"""One-to-one matching never implies liveness or document authenticity."""

import math
import time

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
from app.schemas.faces import DetectionData, VerificationData
from app.settings import load_config


def detect_faces(
    image: np.ndarray, engine: FaceEngine | None = None
) -> LayerResult[DetectionData]:
    validate_image_array(image)
    start = time.perf_counter()
    result = LayerResult(data=DetectionData())
    try:
        observations, _ = (engine or get_engine()).detect(image)
        result.data.faces = observations
        result.data.face_count = len(observations)
        if not observations:
            result.status = "insufficient_evidence"
            result.findings.append(
                Finding(code="NO_FACE", explanation="No face detected.")
            )
    except (ModelUnavailable, cv2.error) as exc:
        result.status = "unavailable"
        result.findings.append(
            Finding(
                code="FACE_MODEL_UNAVAILABLE",
                explanation=str(exc)
                if isinstance(exc, ModelUnavailable)
                else "Face inference failed.",
            )
        )
    result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
    return result


def verify_faces(
    document: np.ndarray,
    live: np.ndarray,
    threshold: float | None = None,
    engine: FaceEngine | None = None,
) -> LayerResult[VerificationData]:
    validate_image_array(document)
    validate_image_array(live)
    override = threshold is not None
    threshold = (
        load_config("face_thresholds.yaml")["cosine_threshold"]
        if threshold is None
        else threshold
    )
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError("Cosine threshold must be finite and between -1 and 1.")
    start = time.perf_counter()
    data = VerificationData(threshold=threshold)
    if override:
        data.threshold_source = "request_override"
    result = LayerResult(data=data)
    try:
        engine = engine or get_engine()
        doc_faces, doc_rows = engine.detect(document)
        live_faces, live_rows = engine.detect(live)
        data.document_face_count, data.live_face_count = len(doc_faces), len(live_faces)
        data.document_face = doc_faces[0] if len(doc_faces) == 1 else None
        data.live_face = live_faces[0] if len(live_faces) == 1 else None
        data.model_sha256 = engine.model_sha256
        for name, faces in [("document", doc_faces), ("live", live_faces)]:
            if len(faces) != 1:
                result.findings.append(
                    Finding(
                        code="NO_FACE" if not faces else "MULTIPLE_FACES",
                        field=name,
                        severity="medium",
                        explanation=f"{name}: expected one face; found {len(faces)}.",
                    )
                )
            elif not faces[0].quality_ok:
                result.findings.append(
                    Finding(
                        code="FACE_QUALITY",
                        field=name,
                        severity="medium",
                        explanation=f"{name}: {', '.join(faces[0].quality_reasons)}.",
                    )
                )
        if result.findings:
            result.status = "insufficient_evidence"
        else:
            similarity = cosine_similarity(
                engine.embedding(document, doc_rows[0]),
                engine.embedding(live, live_rows[0]),
            )
            data.cosine_similarity = similarity
            data.match = similarity >= threshold
            data.decision = "match" if data.match else "non_match"
            result.findings.append(
                Finding(
                    code="FACE_MATCH" if data.match else "FACE_NON_MATCH",
                    severity="info" if data.match else "medium",
                    explanation=f"Cosine {similarity:.4f}; "
                    f"demo threshold {threshold:.4f}. "
                    "This does not verify liveness or document authenticity.",
                )
            )
    except (ModelUnavailable, cv2.error) as exc:
        result.status = "unavailable"
        result.findings.append(
            Finding(
                code="FACE_MODEL_UNAVAILABLE",
                explanation=str(exc)
                if isinstance(exc, ModelUnavailable)
                else "Face inference failed.",
            )
        )
    result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
    return result
