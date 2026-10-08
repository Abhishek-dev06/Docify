"""Actually train a tiny U-Net; select checkpoint on validation, evaluate test once."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from app.layers.l3_tampering.network import TinyUNet
from app.settings import ROOT
from torch import nn


def load_data(directory: Path) -> tuple[dict, list]:
    records = json.loads((directory / "manifest.json").read_text())
    if any(r.get("source") != "procedural-synthetic-v1" for r in records):
        raise ValueError(
            "This recipe reports procedural-synthetic-v1 metrics only. "
            "Adapt provenance, splits and evaluation before training public data."
        )
    groups: dict[str, str] = {}
    splits = {s: [] for s in ("train", "val", "test")}
    for record in records:
        group, split = record["group"], record["split"]
        if group in groups and groups[group] != split:
            raise ValueError("Identity/source group leaks between splits.")
        groups[group] = split
        image = cv2.imread(str(directory / record["image"]))
        mask = cv2.imread(str(directory / record["mask"]), cv2.IMREAD_GRAYSCALE)
        if image is None or mask is None or image.shape[:2] != mask.shape:
            raise ValueError("Missing or misaligned image/mask.")
        image = cv2.resize(image, (192, 192))[:, :, ::-1].copy()
        mask = cv2.resize(mask, (192, 192), interpolation=cv2.INTER_NEAREST)
        splits[split].append(
            (image.transpose(2, 0, 1) / 255.0, mask[None] > 127, record)
        )
    if any(not rows for rows in splits.values()):
        raise ValueError("All three splits must contain samples.")
    result = {}
    for name, rows in splits.items():
        result[name] = (
            torch.tensor(np.asarray([x[0] for x in rows]), dtype=torch.float32),
            torch.tensor(np.asarray([x[1] for x in rows]), dtype=torch.float32),
            [x[2] for x in rows],
        )
    return result, records


def evaluate(model: TinyUNet, x: torch.Tensor, y: torch.Tensor, rows: list) -> dict:
    model.eval()
    with torch.inference_mode():
        probs = torch.cat([model(batch).sigmoid() for batch in x.split(8)])
    pred = probs >= 0.5
    truth = y > 0.5
    image_pred = pred.flatten(1).float().mean(1) >= 0.02
    image_true = truth.flatten(1).any(1)
    tp = int((image_pred & image_true).sum())
    fp = int((image_pred & ~image_true).sum())
    fn = int((~image_pred & image_true).sum())
    tn = int((~image_pred & ~image_true).sum())
    precision, recall = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    per_attack = {}
    for attack in sorted({r["attack"] for r in rows}):
        indices = [i for i, r in enumerate(rows) if r["attack"] == attack]
        a, b = pred[indices], truth[indices]
        intersection = (a & b).flatten(1).sum(1).float()
        union = (a | b).flatten(1).sum(1).float()
        per_attack[attack] = {
            "count": len(indices),
            "flagged": int(image_pred[indices].sum()),
            "mean_iou": float((intersection / union.clamp_min(1)).mean())
            if attack != "clean"
            else None,
            "mean_predicted_fraction": float(a.float().mean()),
        }
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(precision + recall, 1e-8),
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "per_attack": per_attack,
        "pixel_threshold": 0.5,
        "image_fraction_threshold": 0.02,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "tampering")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "models" / "tamper_unet.pt"
    )
    args = parser.parse_args()
    if not 1 <= args.epochs <= 500 or not 1 <= args.threads <= 16:
        parser.error("epochs 1..500 and threads 1..16 required.")
    torch.set_num_threads(args.threads)
    torch.manual_seed(310)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    data, records = load_data(args.data)
    x, y, _ = data["train"]
    model = TinyUNet()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.002)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([3.0]))
    history, best, best_state = [], float("inf"), None
    for epoch in range(args.epochs):
        model.train()
        order = torch.randperm(len(x))
        total = 0.0
        for indices in order.split(8):
            optimizer.zero_grad()
            logits = model(x[indices])
            loss = criterion(logits, y[indices])
            loss.backward()
            optimizer.step()
            total += float(loss.detach()) * len(indices)
        model.eval()
        with torch.inference_mode():
            vx, vy, _ = data["val"]
            val = sum(
                float(criterion(model(vx[i : i + 8]), vy[i : i + 8]))
                * len(vx[i : i + 8])
                for i in range(0, len(vx), 8)
            ) / len(vx)
        history.append(
            {"epoch": epoch + 1, "train_loss": total / len(x), "val_loss": val}
        )
        if val < best:
            best = val
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        print(json.dumps(history[-1]), flush=True)
    model.load_state_dict(best_state)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, args.output)
    manifest = {
        "architecture": "tiny-unet-v1",
        "input_size": 192,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "training_domain": "procedural-synthetic-v1",
        "calibrated": False,
        "dataset_manifest_sha256": hashlib.sha256(
            (args.data / "manifest.json").read_bytes()
        ).hexdigest(),
    }
    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2))
    report = {
        **manifest,
        "torch_version": torch.__version__,
        "seed": 310,
        "seconds": time.perf_counter() - started,
        "split_counts": {s: len(v[0]) for s, v in data.items()},
        "unique_groups": len({r["group"] for r in records}),
        "history": history,
        "test": evaluate(model, *data["test"]),
        "limitations": [
            "Synthetic-only; fixed template and attack generator.",
            "Identity groups held out; layouts and attack families overlap.",
            "No public-dataset or real-document accuracy claim.",
        ],
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "phase3_training.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["test"], indent=2))


if __name__ == "__main__":
    main()
