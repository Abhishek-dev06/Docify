"""Bounded image decoding, quadrilateral correction and quality checks."""

import base64
import io
import time
import warnings

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.schemas.common import DocumentType, Finding, LayerResult
from app.schemas.documents import CaptureData, Quality
from app.settings import MAX_IMAGE_PIXELS, MAX_UPLOAD_BYTES, load_config


def decode_image(payload: bytes) -> np.ndarray:
    if not payload or len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("Image is empty or exceeds the 10 MiB upload limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Supported formats: JPEG, PNG and WEBP.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image exceeds the 20 megapixel limit.")
                rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"))
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Invalid or unsafe image payload.") from exc
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def encode_image(image: np.ndarray) -> str:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Image encoding failed.")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def order_corners(points: np.ndarray) -> np.ndarray:
    """Order four convex corners clockwise, beginning at top left."""
    points = points.reshape(4, 2).astype(np.float32)
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    points = points[np.argsort(angles)]
    return np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)


def correct_perspective(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 130)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        area = cv2.contourArea(contour)
        if not 0.35 * height * width <= area <= 0.995 * height * width:
            continue
        polygon = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        corners = order_corners(polygon)
        tl, tr, br, bl = corners
        out_w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
        out_h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
        if min(out_w, out_h) < 100:
            continue
        target = np.float32(
            [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]]
        )
        transform = cv2.getPerspectiveTransform(corners, target)
        return cv2.warpPerspective(image, transform, (out_w, out_h)), transform, True
    return image.copy(), np.eye(3), False


def preprocess(
    image: np.ndarray, document_type: DocumentType = "unknown"
) -> LayerResult[CaptureData]:
    """Transform is relative to the EXIF-oriented input, before resizing."""
    started = time.perf_counter()
    if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 2:
        raise ValueError("Expected a nonempty BGR image with three channels.")
    cfg = load_config("quality_thresholds.yaml")
    scale = min(1.0, cfg["max_processing_dimension"] / max(image.shape[:2]))
    resized = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
    corrected, transform, detected = correct_perspective(resized)
    transform = transform @ np.diag([scale, scale, 1.0])
    gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    quality = Quality(
        width=width,
        height=height,
        laplacian_variance=round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
        brightness=round(float(gray.mean()), 3),
        saturated_fraction=round(float(np.mean(np.all(corrected >= 253, axis=2))), 5),
    )
    failures: list[Finding] = []
    tests = [
        (
            width < cfg["min_width"] or height < cfg["min_height"],
            "LOW_RESOLUTION",
            "Document resolution is too low; move closer and rescan.",
        ),
        (
            quality.laplacian_variance < cfg["min_laplacian_variance"],
            "BLUR",
            "Image appears blurred; stabilize the camera and refocus.",
        ),
        (
            quality.brightness < cfg["min_brightness"],
            "DARK",
            "Image is too dark; improve diffuse lighting.",
        ),
        (
            quality.brightness > cfg["max_brightness"],
            "OVEREXPOSED",
            "Image is overexposed; reduce direct illumination.",
        ),
        (
            quality.saturated_fraction > cfg["max_saturated_fraction"],
            "POSSIBLE_GLARE",
            "Large saturated regions may hide text; change the angle.",
        ),
    ]
    for failed, code, explanation in tests:
        if failed:
            failures.append(
                Finding(code=code, severity="medium", explanation=explanation)
            )
    findings = list(failures)
    if not detected:
        findings.append(
            Finding(
                code="BOUNDARY_NOT_FOUND",
                explanation=(
                    "Using the full image; suitable for an already-cropped document."
                ),
            )
        )
    # Geometry cannot reliably distinguish visa, license and permit layouts.
    confidence = None
    method = "user_hint" if document_type != "unknown" else "geometry_abstention"
    if document_type == "unknown" and 1.48 <= width / height <= 1.68:
        document_type, confidence, method = "id", 0.35, "aspect_ratio_heuristic"
        findings.append(
            Finding(
                code="TYPE_UNCERTAIN",
                explanation=(
                    "ID-like aspect ratio only; OCR keywords may revise the type."
                ),
            )
        )
    return LayerResult(
        status="needs_rescan" if failures else "ok",
        data=CaptureData(
            document_type=document_type,
            classification_confidence=confidence,
            classification_method=method,
            boundary_detected=detected,
            quality=quality,
            image_base64=encode_image(corrected),
            transform=transform.tolist(),
        ),
        findings=findings,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
