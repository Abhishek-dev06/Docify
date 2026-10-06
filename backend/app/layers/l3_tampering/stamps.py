"""Color candidates plus template comparison; optional one-class YOLOv8 ONNX."""

import hashlib
import os
from pathlib import Path

import cv2
import numpy as np

from app.schemas.tampering import DetectorEvidence


def demo_template() -> np.ndarray:
    template = np.full((64, 64, 3), 235, np.uint8)
    cv2.circle(template, (32, 32), 26, (70, 65, 170), 2)
    cv2.putText(
        template,
        "DEMO",
        (11, 36),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (70, 65, 170),
        1,
        cv2.LINE_AA,
    )
    return template


def compare_template(crop: np.ndarray, template: np.ndarray) -> float:
    a = cv2.Canny(cv2.cvtColor(cv2.resize(crop, (64, 64)), cv2.COLOR_BGR2GRAY), 50, 150)
    b = cv2.Canny(
        cv2.cvtColor(cv2.resize(template, (64, 64)), cv2.COLOR_BGR2GRAY), 50, 150
    )
    if not a.any() or not b.any():
        return 0.0
    best = 0.0
    for angle in (-10, 0, 10):
        rotation = cv2.getRotationMatrix2D((32, 32), angle, 1)
        rotated = cv2.warpAffine(b, rotation, (64, 64))
        value = cv2.matchTemplate(a, rotated, cv2.TM_CCOEFF_NORMED)[0, 0]
        best = max(best, float(value))
    return best


def decode_yolo(output: np.ndarray, shape: tuple, size: int = 640) -> list[tuple]:
    """Accept only YOLOv8 one-class [1,5,N] raw output, without embedded NMS."""
    if output.ndim != 3 or output.shape[:2] != (1, 5) or not np.isfinite(output).all():
        raise ValueError("Expected finite one-class YOLOv8 [1,5,N] output.")
    h, w = shape[:2]
    scale = min(size / w, size / h)
    pad_x, pad_y = (size - round(w * scale)) // 2, (size - round(h * scale)) // 2
    boxes, confidences = [], []
    for cx, cy, bw, bh, confidence in output[0].T:
        if confidence < 0.4 or confidence > 1 or min(bw, bh) <= 0:
            continue
        x1 = float(np.clip((cx - bw / 2 - pad_x) / scale, 0, w))
        y1 = float(np.clip((cy - bh / 2 - pad_y) / scale, 0, h))
        x2 = float(np.clip((cx + bw / 2 - pad_x) / scale, 0, w))
        y2 = float(np.clip((cy + bh / 2 - pad_y) / scale, 0, h))
        if x2 - x1 < 4 or y2 - y1 < 4:
            continue
        boxes.append([int(x1), int(y1), int(x2 - x1), int(y2 - y1)])
        confidences.append(float(confidence))
    indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.4, 0.45)
    return [tuple(boxes[int(i)]) for i in np.asarray(indices).flatten()[:20]]


def yolo_boxes(image: np.ndarray) -> list[tuple] | None:
    value = os.getenv("STAMP_YOLO_PATH")
    if not value:
        return None
    path = Path(value)
    expected = os.getenv("STAMP_YOLO_SHA256", "")
    if not path.is_file() or len(expected) != 64:
        raise ValueError("Stamp model or configured checksum missing.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("Stamp model checksum mismatch.")
    h, w = image.shape[:2]
    scale = min(640 / w, 640 / h)
    resized = cv2.resize(image, (round(w * scale), round(h * scale)))
    canvas = np.full((640, 640, 3), 114, np.uint8)
    ph, pw = (640 - resized.shape[0]) // 2, (640 - resized.shape[1]) // 2
    canvas[ph : ph + resized.shape[0], pw : pw + resized.shape[1]] = resized
    net = cv2.dnn.readNetFromONNX(str(path))
    net.setInput(cv2.dnn.blobFromImage(canvas, 1 / 255.0, swapRB=True))
    return decode_yolo(net.forward(), image.shape)


def analyze_stamps(image: np.ndarray) -> list[DetectorEvidence]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    mask = (
        ((hue < 15) | (hue > 165) | ((hue > 95) & (hue < 135)))
        & (saturation > 70)
        & (value > 40)
    ).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= 80]
    boxes = [b for b in boxes if min(b[2:]) >= 10][:20]
    yolo = DetectorEvidence(
        name="stamp_yolo",
        status="unavailable",
        method="One-class YOLOv8 ONNX adapter",
        explanation="No stamp-trained YOLO weights configured. Color candidates "
        "below are a classical baseline, not YOLO predictions.",
    )
    try:
        learned = yolo_boxes(image)
        if learned is not None:
            boxes = learned
            yolo = DetectorEvidence(
                name="stamp_yolo",
                method="YOLOv8 ONNX candidates",
                explanation="Detected stamp candidates; detection is not authenticity.",
                metrics={"candidate_count": len(boxes)},
            )
    except (ValueError, OSError, cv2.error) as exc:
        yolo.explanation = f"Configured YOLO unavailable ({type(exc).__name__})."
    h, w = image.shape[:2]
    regions = [(x / w, y / h, bw / w, bh / h) for x, y, bw, bh in boxes]
    similarity = [
        compare_template(image[y : y + bh, x : x + bw], demo_template())
        for x, y, bw, bh in boxes
    ]
    template = DetectorEvidence(
        name="stamp_template",
        status="insufficient_evidence",
        method="Edge template matching against a fictional DEMO stamp",
        explanation="Only a synthetic DEMO template is bundled. Similarity cannot "
        "authenticate issuer stamps; verified issuer templates are absent.",
        regions=regions,
        metrics={
            "candidate_count": len(boxes),
            "best_demo_template_similarity": max(similarity) if similarity else None,
            "verified_issuer_templates": False,
        },
    )
    yolo.regions = regions if yolo.status == "ok" else []
    return [yolo, template]
