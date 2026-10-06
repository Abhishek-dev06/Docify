"""Phase 1 orchestration; later phases extend this typed result."""

import base64
import hashlib
import time
from datetime import date

from pydantic import BaseModel

from app.layers.l0_capture.preprocess import decode_image, preprocess
from app.layers.l1_ocr.engine import extract_ocr
from app.layers.l2_validation.checks import validate_document
from app.schemas.common import DocumentType, LayerResult, Status
from app.schemas.documents import (
    CaptureData,
    OCRData,
    ValidationData,
    ValidationRequest,
)


class Phase1Result(BaseModel):
    status: Status
    document_hash: str
    capture: LayerResult[CaptureData]
    ocr: LayerResult[OCRData] | None = None
    validation: LayerResult[ValidationData] | None = None
    duration_ms: float


def analyze_phase1(
    payload: bytes,
    reference_date: date,
    document_type: DocumentType = "unknown",
    db_url: str | None = None,
) -> Phase1Result:
    started = time.perf_counter()
    capture = preprocess(decode_image(payload), document_type)
    ocr = None
    validation = None
    status = capture.status
    if status == "ok":
        corrected = decode_image(base64.b64decode(capture.data.image_base64))
        ocr = extract_ocr(corrected, document_type)
        status = ocr.status
        if ocr.status == "ok":
            validation = validate_document(
                ValidationRequest(
                    document_type=ocr.data.document_type,
                    reference_date=reference_date,
                    mrz=ocr.data.mrz,
                    viz_fields=ocr.data.viz_fields,
                ),
                db_url,
            )
            status = validation.status
    return Phase1Result(
        status=status,
        document_hash=hashlib.sha256(payload).hexdigest(),
        capture=capture,
        ocr=ocr,
        validation=validation,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
