"""Prepare authorized image/mask pairs, keeping document/identity groups together."""

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from app.layers.l0_capture.preprocess import decode_image
from app.layers.l3_tampering.synthetic import split_group
from PIL import Image


def inside(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Manifest paths must remain inside the source root.")
    return path


def prepare(source: Path, manifest: Path, output: Path, size: int = 192) -> list[dict]:
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    if not 32 <= size <= 2048:
        raise ValueError("Output size must be 32..2048.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory.")
    prepared, seen_hashes = [], {}
    output.mkdir(parents=True, exist_ok=True)
    for i, row in enumerate(rows):
        group = row["group"]
        if not isinstance(group, str) or not group.strip():
            raise ValueError("Every row needs a stable source-document/identity group.")
        payload = inside(source, row["image"]).read_bytes()
        # Reject non-upright input rather than silently misaligning original masks.
        with Image.open(inside(source, row["image"])) as original:
            if original.getexif().get(274, 1) != 1:
                raise ValueError(
                    "Normalize image AND mask orientation before importing."
                )
        image = decode_image(payload)
        split = row.get("split", split_group(group))
        if split not in {"train", "val", "test"}:
            raise ValueError("Invalid split.")
        digest = hashlib.sha256(image.tobytes()).hexdigest()
        if digest in seen_hashes and seen_hashes[digest] != split:
            raise ValueError("Identical decoded image leaks across splits.")
        seen_hashes[digest] = split
        if row.get("mask"):
            mask = cv2.imread(str(inside(source, row["mask"])), cv2.IMREAD_GRAYSCALE)
            if mask is None or mask.shape != image.shape[:2]:
                raise ValueError("Mask must exist and align exactly with its image.")
            mask = (mask > 0).astype(np.uint8) * 255
        elif row.get("attack") == "clean" and row.get("verified_clean") is True:
            mask = np.zeros(image.shape[:2], np.uint8)
        else:
            raise ValueError("Unknown labels are not clean; provide an explicit mask.")
        attack = row["attack"]
        if (attack == "clean") != (not mask.any()):
            raise ValueError("Clean/attack label disagrees with mask.")
        image = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask, (size, size), interpolation=cv2.INTER_NEAREST)
        image_name, mask_name = f"{i:07d}.png", f"{i:07d}_mask.png"
        cv2.imwrite(str(output / image_name), image)
        cv2.imwrite(str(output / mask_name), mask)
        prepared.append(
            {
                "image": image_name,
                "mask": mask_name,
                "group": group,
                "split": split,
                "attack": attack,
                "source": row.get("source", "user-authorized-public-dataset"),
                "source_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    groups = {}
    for row in prepared:
        if row["group"] in groups and groups[row["group"]] != row["split"]:
            raise ValueError("Source-document/identity group leaks across splits.")
        groups[row["group"]] = row["split"]
    (output / "manifest.json").write_text(
        json.dumps(prepared, indent=2), encoding="utf-8"
    )
    return prepared


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"Prepared {len(prepare(args.source, args.manifest, args.output))} samples.")
