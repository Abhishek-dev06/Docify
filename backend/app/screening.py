"""L0 -> L1 -> parallel L2/L3/L4 -> L5, without image persistence."""

import base64
import hashlib
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import cv2
import numpy as np
from pydantic import BaseModel, Field

from app.layers.l0_capture.preprocess import decode_image, preprocess
from app.layers.l1_ocr.engine import extract_ocr
from app.layers.l2_validation.checks import validate_document
from app.layers.l3_tampering.analyzer import analyze_tampering
from app.layers.l3_tampering.classical import validate_region
from app.layers.l4_face.liveness import evaluate_liveness
from app.layers.l4_face.verification import verify_faces
from app.layers.l5_risk.engine import score_risk
from app.layers.l5_risk.evidence import risk_inputs
from app.schemas.common import DocumentType, Finding, LayerResult, Status
from app.schemas.documents import (
    CaptureData,
    OCRData,
    ValidationData,
    ValidationRequest,
)
from app.schemas.faces import LivenessData, VerificationData
from app.schemas.risk import RiskData
from app.schemas.tampering import TamperingData
from app.settings import load_config

# A shared bounded pool prevents each simultaneous request spawning more CPU workers.
LAYER_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="screening-layer")


class StageFailure(BaseModel):
    stage: str
    code: str
    explanation: str = "Layer processing failed; evidence remains unavailable."


class ScreeningResult(BaseModel):
    status: Status
    document_hash: str
    reference_date: date
    capture: LayerResult[CaptureData]
    ocr: LayerResult[OCRData] | None = None
    validation: LayerResult[ValidationData] | None = None
    tampering: LayerResult[TamperingData] | None = None
    face: LayerResult[VerificationData] | None = None
    liveness: LayerResult[LivenessData] | None = None
    risk: LayerResult[RiskData]
    failures: list[StageFailure] = Field(default_factory=list)
    duration_ms: float
    parallel_stage_ms: float = 0
    images_persisted: bool = False
    face_coordinate_frame: str = "L0-corrected document and supplied live/frame image"


def frame_inputs(live_payload, frames, timestamps_ms):
    cfg = load_config("face_thresholds.yaml")
    if live_payload is not None and frames is not None:
        raise ValueError("Supply live or ordered frames, not both.")
    if frames is None and timestamps_ms is not None:
        raise ValueError("timestamps_ms requires frames.")
    if frames is not None:
        if not 1 <= len(frames) <= cfg["max_frames"]:
            raise ValueError("Provide 1..12 ordered frames.")
        if timestamps_ms is None and len(frames) > 1:
            raise ValueError("Multiple frames require timestamps_ms.")
        if timestamps_ms is not None and (
            not isinstance(timestamps_ms, list)
            or len(timestamps_ms) != len(frames)
            or any(
                isinstance(t, bool)
                or not isinstance(t, (float, int))
                or not math.isfinite(t)
                or not 0 <= t <= 20000
                for t in timestamps_ms
            )
            or any(
                b <= a for a, b in zip(timestamps_ms, timestamps_ms[1:], strict=False)
            )
        ):
            raise ValueError(
                "Timestamps must increase within 0..20000 ms, one per frame."
            )
    payloads = (
        frames
        if frames is not None
        else [live_payload]
        if live_payload is not None
        else []
    )
    images = []
    pixels = 0
    for payload in payloads:
        image = decode_image(payload)
        pixels += image.shape[0] * image.shape[1]
        if pixels > cfg["max_sequence_pixels"]:
            raise ValueError(
                "Live/frame images exceed the 12 megapixel sequence budget."
            )
        images.append(image)
    return images


def screen_document(
    payload: bytes,
    reference_date: date,
    document_type: DocumentType = "unknown",
    live_payload: bytes | None = None,
    photo_region: tuple | None = None,
    frames: list[bytes] | None = None,
    timestamps_ms: list[float] | None = None,
    db_url: str | None = None,
) -> ScreeningResult:
    started = time.perf_counter()
    if photo_region is not None:
        photo_region = validate_region(photo_region)
    images = frame_inputs(live_payload, frames, timestamps_ms)
    original = decode_image(payload)
    capture = preprocess(original, document_type)
    common = dict(
        document_hash=hashlib.sha256(payload).hexdigest(),
        reference_date=reference_date,
        capture=capture,
    )
    if capture.status != "ok":
        unknown_risk = score_risk(risk_inputs())
        unknown_risk.data.evidence_origin = "server_layers"
        return ScreeningResult(
            **common,
            status=capture.status,
            risk=unknown_risk,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    corrected = decode_image(base64.b64decode(capture.data.image_base64))
    ocr_image = corrected
    if photo_region is not None:
        # Map the caller-specified portrait from original pixels into the L0 crop.
        # Keep the unmasked image for face comparison and original bytes for L3.
        x, y, w, h = photo_region
        oh, ow = original.shape[:2]
        corners = np.float32(
            [
                [
                    [x * ow, y * oh],
                    [(x + w) * ow, y * oh],
                    [(x + w) * ow, (y + h) * oh],
                    [x * ow, (y + h) * oh],
                ]
            ]
        )
        mapped = cv2.perspectiveTransform(corners, np.asarray(capture.data.transform))
        ocr_image = corrected.copy()
        cv2.fillConvexPoly(
            ocr_image, np.round(mapped[0]).astype(np.int32), (255, 255, 255)
        )
    failures = []
    ocr = None
    try:
        ocr = extract_ocr(ocr_image, document_type)
        if photo_region is not None:
            ocr.findings.append(
                Finding(
                    code="PORTRAIT_EXCLUDED_FROM_OCR",
                    explanation="Caller-specified portrait excluded from OCR only; "
                    "L3 and face comparison retain the original image evidence.",
                    region=photo_region,
                )
            )
    except Exception as exc:
        failures.append(StageFailure(stage="L1", code=type(exc).__name__))
    request = ValidationRequest(
        reference_date=reference_date,
        document_type=ocr.data.document_type if ocr else document_type,
        mrz=ocr.data.mrz if ocr and ocr.status == "ok" else None,
        viz_fields=ocr.data.viz_fields if ocr and ocr.status == "ok" else {},
    )

    def face_stage():
        if not images:
            return None, None, []
        # First submitted sequence frame is also the face-comparison reference.
        results, errors = [], []
        for name, call in [
            ("L4.face", lambda: verify_faces(corrected, images[0])),
            ("L4.liveness", lambda: evaluate_liveness(images, timestamps_ms)),
        ]:
            try:
                results.append(call())
            except Exception as exc:
                errors.append(StageFailure(stage=name, code=type(exc).__name__))
                results.append(None)
        return *results, errors

    parallel_start = time.perf_counter()
    futures = {
        "L2": LAYER_POOL.submit(validate_document, request, db_url),
        "L3": LAYER_POOL.submit(analyze_tampering, payload, photo_region),
        "L4": LAYER_POOL.submit(face_stage),
    }
    results = {}
    for name, future in futures.items():
        try:
            results[name] = future.result()
        except Exception as exc:
            # Preserve successes from other layers; never synthesize zero-risk results.
            failures.append(StageFailure(stage=name, code=type(exc).__name__))
            results[name] = None
    parallel_ms = round((time.perf_counter() - parallel_start) * 1000, 2)
    face, liveness, face_errors = results.get("L4") or (None, None, [])
    failures.extend(face_errors)
    risk = score_risk(risk_inputs(results["L2"], results["L3"], face, liveness))
    risk.data.evidence_origin = "server_layers"
    return ScreeningResult(
        **common,
        status="insufficient_evidence" if failures else risk.status,
        ocr=ocr,
        validation=results["L2"],
        tampering=results["L3"],
        face=face,
        liveness=liveness,
        risk=risk,
        failures=failures,
        parallel_stage_ms=parallel_ms,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
