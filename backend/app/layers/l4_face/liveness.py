"""Untrained anti-spoof indicators; no uploaded image is certified as live."""

import hashlib
import math
import time
from pathlib import Path

import cv2
import numpy as np

from app.layers.l4_face.engine import (
    FaceEngine,
    ModelUnavailable,
    cosine_similarity,
    get_engine,
    validate_image_array,
)
from app.schemas.common import Finding, LayerResult
from app.schemas.faces import FrameEvidence, LivenessData
from app.settings import load_config


def texture_features(face: np.ndarray) -> tuple[float, float]:
    gray = cv2.cvtColor(cv2.resize(face, (128, 128)), cv2.COLOR_BGR2GRAY).astype(
        np.float32
    )
    contrast = float(gray.std())
    gray -= gray.mean()
    window = np.outer(np.hanning(128), np.hanning(128))
    power = np.abs(np.fft.fftshift(np.fft.fft2(gray * window))) ** 2
    y, x = np.ogrid[-64:64, -64:64]
    radius = np.sqrt(x * x + y * y) / 128
    values = power[(radius >= 0.15) & (radius <= 0.45)]
    total = float(values.sum())
    periodic = float(np.sort(values)[-8:].sum() / total) if total > 1e-8 else 0.0
    return contrast, periodic


def visible_eyes(image: np.ndarray, row: np.ndarray) -> int | None:
    path = Path(cv2.data.haarcascades) / "haarcascade_eye_tree_eyeglasses.xml"
    if not path.is_file():
        return None
    cascade = cv2.CascadeClassifier(str(path))
    if cascade.empty():
        return None
    x, y, width, height = row[:4]
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2 = min(image.shape[1], int(x + width))
    y2 = min(image.shape[0], int(y + height * 0.6))
    gray = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    eyes = cascade.detectMultiScale(gray, 1.1, 4, minSize=(12, 12))
    halves = set()
    for ex, _ey, ew, _eh in eyes:
        halves.add(int(ex + ew / 2 >= gray.shape[1] / 2))
    return len(halves)


def blink_candidate(frames: list[FrameEvidence], cfg: dict) -> bool:
    """Two open observations, a brief zero-eye interval, then two open ones."""
    if len(frames) < cfg["min_blink_frames"] or any(
        not f.quality_ok or f.same_face_as_first is not True for f in frames
    ):
        return False
    times = [f.timestamp_ms for f in frames]
    if any(
        b - a > cfg["max_frame_gap_ms"] for a, b in zip(times, times[1:], strict=False)
    ):
        return False
    for start in range(2, len(frames) - 2):
        if [f.eyes_visible for f in frames[start - 2 : start]] != [2, 2]:
            continue
        if frames[start].eyes_visible != 0:
            continue
        end = start
        while end < len(frames) and frames[end].eyes_visible == 0:
            end += 1
        if end + 1 >= len(frames):
            continue
        duration = frames[end].timestamp_ms - frames[start].timestamp_ms
        if (
            frames[end].eyes_visible == frames[end + 1].eyes_visible == 2
            and cfg["min_blink_duration_ms"] <= duration <= cfg["max_blink_duration_ms"]
        ):
            return True
    return False


def evaluate_liveness(
    images: list[np.ndarray],
    timestamps_ms: list[float] | None = None,
    engine: FaceEngine | None = None,
) -> LayerResult[LivenessData]:
    cfg = load_config("face_thresholds.yaml")
    if not 1 <= len(images) <= cfg["max_frames"]:
        raise ValueError(f"Provide 1 to {cfg['max_frames']} ordered frames.")
    for image in images:
        validate_image_array(image)
    if sum(im.shape[0] * im.shape[1] for im in images) > cfg["max_sequence_pixels"]:
        raise ValueError("Total frame pixel count exceeds the sequence limit.")
    if timestamps_ms is None:
        if len(images) != 1:
            raise ValueError("Multiple frames require timestamps_ms.")
        timestamps_ms = [0.0]
    if (
        len(timestamps_ms) != len(images)
        or any(not math.isfinite(t) or not 0 <= t <= 20000 for t in timestamps_ms)
        or any(b <= a for a, b in zip(timestamps_ms, timestamps_ms[1:], strict=False))
    ):
        raise ValueError(
            "Timestamps must strictly increase within 0..20000 ms, one per frame."
        )
    started = time.perf_counter()
    data = LivenessData()
    result = LayerResult(data=data)
    try:
        engine = engine or get_engine()
        first_embedding = None
        digests = set()
        indicators = []
        for index, (image, timestamp) in enumerate(
            zip(images, timestamps_ms, strict=True)
        ):
            digest = hashlib.sha256(image.tobytes()).digest()
            if digest in digests:
                data.repeated_frame_count += 1
            digests.add(digest)
            faces, rows = engine.detect(image)
            evidence = FrameEvidence(
                index=index, timestamp_ms=timestamp, face_count=len(faces)
            )
            if len(faces) == 1 and faces[0].quality_ok:
                row = rows[0]
                current = engine.embedding(image, row)
                if first_embedding is None:
                    first_embedding = current
                evidence.same_face_as_first = (
                    cosine_similarity(first_embedding, current)
                    >= cfg["cosine_threshold"]
                )
                evidence.quality_ok = True
                evidence.eyes_visible = visible_eyes(image, row)
                x, y, w, h = faces[0].box
                height, width = image.shape[:2]
                patch = image[
                    int(y * height) : max(int((y + h) * height), int(y * height) + 1),
                    int(x * width) : max(int((x + w) * width), int(x * width) + 1),
                ]
                contrast, periodic = texture_features(patch)
                evidence.texture_contrast = round(contrast, 4)
                evidence.periodic_energy_ratio = round(periodic, 4)
                indicator = 0.5 * (contrast < 8) + 0.5 * (periodic > 0.45)
                indicators.append(indicator)
            else:
                result.findings.append(
                    Finding(
                        code="LIVENESS_FACE_EVIDENCE_MISSING",
                        field=f"frames[{index}]",
                        severity="medium",
                        explanation="Each frame needs exactly one clear face.",
                    )
                )
            data.frames.append(evidence)
        data.blink_candidate = blink_candidate(data.frames, cfg)
        if indicators:
            data.spoof_indicator_score = float(max(indicators))
        if len(images) > 1 and data.repeated_frame_count == len(images) - 1:
            data.spoof_indicator_score = 1.0
            result.findings.append(
                Finding(
                    code="REPEATED_FRAMES",
                    severity="medium",
                    explanation="Identical frames provide no temporal evidence.",
                )
            )
        if any(frame.same_face_as_first is False for frame in data.frames):
            result.findings.append(
                Finding(
                    code="FACE_CONTINUITY_FAILED",
                    severity="medium",
                    explanation="Face continuity failed; sequence needs review.",
                )
            )
        if data.spoof_indicator_score is not None and data.spoof_indicator_score >= 0.5:
            data.verdict = "suspicious"
            result.findings.append(
                Finding(
                    code="SPOOF_HEURISTIC",
                    severity="low",
                    explanation=(
                        "Untrained texture/repetition indicator; "
                        "lighting and capture can cause false alarms."
                    ),
                )
            )
        result.status = (
            "insufficient_evidence" if len(images) == 1 or result.findings else "ok"
        )
        result.findings.append(
            Finding(
                code="LIVENESS_NOT_VERIFIED",
                explanation=(
                    "Blink candidates and texture statistics are review evidence only; "
                    "no live-person decision or calibrated liveness score is produced."
                ),
            )
        )
    except (ModelUnavailable, cv2.error) as exc:
        result.status = "unavailable"
        result.findings.append(
            Finding(
                code="FACE_MODEL_UNAVAILABLE",
                explanation=str(exc)
                if isinstance(exc, ModelUnavailable)
                else "Liveness inference failed.",
            )
        )
    result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
    return result
