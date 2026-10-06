"""Optional, hash-verified synthetic checkpoint inference."""

import hashlib
import json
import os
import pickle
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from app.layers.l3_tampering.classical import regions_from_map
from app.schemas.tampering import DetectorEvidence
from app.settings import ROOT


@lru_cache(maxsize=2)
def load_model(path: str, digest: str):
    import torch

    from app.layers.l3_tampering.network import TinyUNet

    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
        raise ValueError("Tamper checkpoint checksum mismatch.")
    torch.set_num_threads(2)
    model = TinyUNet()
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    model.eval()
    return model


def predict(image: np.ndarray) -> tuple[DetectorEvidence, np.ndarray | None]:
    path = Path(os.getenv("TAMPER_MODEL_PATH", ROOT / "models" / "tamper_unet.pt"))
    method = "Tiny U-Net / procedural synthetic training"
    if not path.is_file() or not path.with_suffix(".json").is_file():
        return DetectorEvidence(
            name="cnn",
            status="unavailable",
            method=method,
            explanation="Synthetic checkpoint missing; run train_tamper_model.py.",
        ), None
    try:
        import torch

        manifest = json.loads(path.with_suffix(".json").read_text())
        if (
            manifest["architecture"] != "tiny-unet-v1"
            or manifest["input_size"] != 192
            or manifest["training_domain"] != "procedural-synthetic-v1"
        ):
            raise ValueError("Unsupported model manifest.")
        # Rehash cached inference to reject a changed checkpoint.
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != manifest["sha256"]:
            raise ValueError("Tamper checkpoint checksum mismatch.")
        model = load_model(str(path.resolve()), digest)
        resized = cv2.resize(image, (192, 192))[:, :, ::-1].copy()
        tensor = torch.from_numpy(resized.transpose(2, 0, 1)).float()[None] / 255
        with torch.inference_mode():
            heat = model(tensor).sigmoid()[0, 0].numpy()
        fraction = float(np.mean(heat >= 0.5))
        score = float(
            np.partition(heat.ravel(), -max(1, heat.size // 100))[
                -max(1, heat.size // 100) :
            ].mean()
        )
        heat = cv2.resize(heat, (image.shape[1], image.shape[0]))
        return DetectorEvidence(
            name="cnn",
            score=score,
            method=method,
            explanation="Learned activation on a fixed procedural mock-card domain; "
            "not a calibrated probability and not validated on real IDs.",
            regions=regions_from_map(heat, 0.5),
            metrics={
                "predicted_fraction": fraction,
                "synthetic_flag": fraction >= 0.02,
                "sha256": digest,
                "calibrated": False,
                "training_domain": manifest["training_domain"],
            },
        ), heat
    except (
        ImportError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        pickle.UnpicklingError,
    ) as exc:
        return DetectorEvidence(
            name="cnn",
            status="unavailable",
            method=method,
            explanation=f"Checkpoint unavailable or invalid ({type(exc).__name__}).",
        ), None
