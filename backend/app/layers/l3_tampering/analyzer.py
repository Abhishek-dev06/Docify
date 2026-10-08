"""Standalone L3 orchestration; original bytes retain metadata/JPEG evidence."""

import time
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from app.layers.l0_capture.preprocess import decode_image, encode_image
from app.layers.l3_tampering import classical
from app.layers.l3_tampering.learned import predict
from app.layers.l3_tampering.stamps import analyze_stamps
from app.schemas.common import LayerResult
from app.schemas.tampering import TamperingData, finding
from app.settings import load_config


def overlay(image: np.ndarray, heat: np.ndarray) -> np.ndarray:
    colors = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    alpha = (heat * 0.65)[:, :, None]
    return np.clip(image * (1 - alpha) + colors * alpha, 0, 255).astype(np.uint8)


def analyze_tampering(
    payload: bytes, photo_region: tuple | None = None, include_cnn: bool = True
) -> LayerResult[TamperingData]:
    started = time.perf_counter()
    config = load_config("tamper_thresholds.yaml")
    original = decode_image(payload)
    image = original
    h, w = original.shape[:2]
    if min(h, w) < 32 or h * w > config["max_forensics_pixels"]:
        raise ValueError("L3 requires images at least 32x32 and at most 4 megapixels.")
    scale = min(1, config["max_dimension"] / max(h, w))
    if scale < 1:
        image = cv2.resize(
            original, (max(1, round(w * scale)), max(1, round(h * scale)))
        )
    with Image.open(BytesIO(payload)) as source:
        is_jpeg = source.format == "JPEG"
    evidence = [classical.metadata(payload), classical.compression(original, is_jpeg)]
    maps = []
    # ELA must be computed before resizing, otherwise a new grid destroys history.
    ela_result, ela_heat = classical.ela(original, is_jpeg, config["ela_quality"])
    evidence.append(ela_result)
    maps.append(cv2.resize(ela_heat, (image.shape[1], image.shape[0])))
    for result, heat in [
        classical.noise(image),
        classical.photo(image, photo_region),
        classical.copy_move(image),
        classical.font_consistency(image),
    ]:
        evidence.append(result)
        maps.append(heat)
    evidence.extend(analyze_stamps(image))
    cnn_heat = None
    if include_cnn:
        learned, cnn_heat = predict(image)
        evidence.append(learned)
    combined = np.maximum.reduce(maps)
    scores = [e.score for e in evidence if e.score is not None and e.name != "cnn"]
    return LayerResult(
        status="ok",
        data=TamperingData(
            suspicion_score=max(scores) if scores else None,
            detectors=evidence,
            heatmap_png_base64=encode_image((combined * 255).astype(np.uint8)),
            overlay_png_base64=encode_image(overlay(image, combined)),
            width=image.shape[1],
            height=image.shape[0],
            cnn_heatmap_png_base64=encode_image((cnn_heat * 255).astype(np.uint8))
            if cnn_heat is not None
            else None,
            limitations=[
                "Scores are uncalibrated review indices, not fraud probabilities.",
                "Text, portraits, compression and printing cause false positives.",
                "Missing detectors remain unavailable; no authenticity verdict.",
                "CNN is procedural-synthetic only; separate from baseline.",
                "Photo region is caller-supplied; issuer stamp templates absent.",
            ],
        ),
        findings=[
            finding(e) for e in evidence if e.score is not None and e.score >= 0.55
        ],
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
