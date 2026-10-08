"""Procedural mock cards and exact operation masks; no real identities."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ATTACKS = ("clean", "text_replacement", "copy_move", "photo_replacement", "stamp_edit")


def synthetic_card(seed: int, size: int = 192) -> np.ndarray:
    rng = np.random.default_rng(seed)
    paper = rng.integers(200, 240, size=3)
    image = np.clip(
        paper + rng.normal(0, rng.uniform(1, 5), (size, size, 1)), 0, 255
    ).astype(np.uint8)
    color = tuple(int(v) for v in rng.integers(30, 100, 3))
    for y in range(8, size, 11):
        cv2.line(image, (0, y), (size - 1, y + 3), (190, 202, 205), 1)
    cv2.putText(
        image,
        "SYNTHETIC / DEMO",
        (8, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.37,
        color,
        1,
        cv2.LINE_AA,
    )
    for row in range(5):
        text = f"DEMO {rng.integers(10000, 99999)}"
        cv2.putText(
            image,
            text,
            (8, 40 + row * 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.32,
            color,
            1,
            cv2.LINE_AA,
        )
    # A procedural face-shaped drawing, not a photograph of a person.
    image[30:118, 127:180] = rng.integers(90, 170, 3)
    cv2.ellipse(image, (153, 65), (17, 24), 0, 0, 360, (160, 180, 210), -1)
    cv2.circle(image, (147, 61), 2, color, -1)
    cv2.circle(image, (159, 61), 2, color, -1)
    cv2.ellipse(image, (153, 109), (22, 23), 0, 180, 360, color, -1)
    cv2.circle(image, (55, 149), 19, (70, 65, 170), 2)
    cv2.putText(
        image, "DEMO", (40, 153), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (70, 65, 170), 1
    )
    cv2.putText(
        image, "UTO<<EXAMPLE<<TEST", (8, 184), cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1
    )
    return image


def make_variant(seed: int, attack: str) -> tuple[np.ndarray, np.ndarray]:
    if attack not in ATTACKS:
        raise ValueError("Unknown synthetic attack.")
    rng = np.random.default_rng(seed + 1031)
    image = synthetic_card(seed)
    mask = np.zeros(image.shape[:2], np.uint8)
    if attack == "text_replacement":
        x, y, w, h = 7, int(rng.integers(1, 5)) * 17 + 26, 111, 16
        image[y : y + h, x : x + w] = rng.integers(225, 256, 3)
        cv2.putText(
            image,
            "EDIT " + str(rng.integers(1000, 9999)),
            (x + 2, y + 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (15, 15, 15),
            1,
        )
        mask[y : y + h, x : x + w] = 255
    elif attack == "copy_move":
        x, y, w, h = 76, 132, 43, 36
        image[y : y + h, x : x + w] = image[130:166, 32:75].copy()
        mask[y : y + h, x : x + w] = 255
    elif attack == "photo_replacement":
        donor = synthetic_card(seed + 100000)
        patch = donor[30:118, 127:180]
        patch = cv2.GaussianBlur(patch, (7, 7), 2)
        image[30:118, 127:180] = np.clip(patch.astype(float) * 1.25, 0, 255)
        mask[30:118, 127:180] = 255
    elif attack == "stamp_edit":
        cv2.circle(image, (55, 149), 19, (230, 230, 230), -1)
        cv2.rectangle(image, (37, 136), (73, 162), (130, 40, 40), 2)
        cv2.putText(
            image, "EDIT", (39, 153), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (130, 40, 40), 1
        )
        cv2.circle(mask, (55, 149), 21, 255, -1)
    # Compression variation is applied to clean and manipulated examples alike.
    _, encoded = cv2.imencode(
        ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(75, 96))]
    )
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR), mask


def split_group(group: str) -> str:
    bucket = int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) % 10
    return "train" if bucket < 7 else "val" if bucket < 9 else "test"


def generate_dataset(output: Path, bases: int = 100) -> list[dict]:
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for seed in range(bases):
        group = f"procedural-card-{seed:05d}"
        for attack in ATTACKS:
            image, mask = make_variant(seed, attack)
            stem = f"{seed:05d}_{attack}"
            cv2.imwrite(str(output / (stem + ".png")), image)
            cv2.imwrite(str(output / (stem + "_mask.png")), mask)
            records.append(
                {
                    "image": stem + ".png",
                    "mask": stem + "_mask.png",
                    "group": group,
                    "split": split_group(group),
                    "attack": attack,
                    "source": "procedural-synthetic-v1",
                }
            )
    (output / "manifest.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    return records
