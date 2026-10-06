"""Small API adapters; processing remains callable without HTTP."""

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.uploads import read_upload, upload_schema
from app.layers.l0_capture.preprocess import decode_image, preprocess
from app.layers.l1_ocr.engine import configure_tesseract, extract_ocr
from app.layers.l1_ocr.mrz import parse_mrz
from app.layers.l2_validation.checks import validate_document
from app.pipeline import Phase1Result, analyze_phase1
from app.schemas.common import DocumentType, LayerResult
from app.schemas.documents import (
    CaptureData,
    MRZData,
    OCRData,
    ValidationData,
    ValidationRequest,
)

router = APIRouter(prefix="/api/v1")


class MRZRequest(BaseModel):
    lines: list[str] = Field(min_length=2, max_length=3)


def document_hint(values: dict[str, str]) -> DocumentType:
    try:
        return TypeAdapter(DocumentType).validate_python(
            values.get("document_type", "unknown")
        )
    except ValidationError as exc:
        raise HTTPException(422, "Unsupported document_type.") from exc


@router.get("/health", tags=["System"])
def health() -> dict:
    return {
        "status": "ok",
        "phase": 6,
        "implemented_layers": ["L0", "L1", "L2", "L3", "L4", "L5", "L6"],
        "ocr_available": configure_tesseract() is not None,
        "images_persisted": False,
        "audit_mode": "opt-in via /scans/analyze; images and identity fields excluded",
        "synthetic_demo_only": True,
    }


@router.post(
    "/capture/preprocess",
    response_model=LayerResult[CaptureData],
    openapi_extra=upload_schema(),
    tags=["L0"],
)
async def capture(request: Request) -> LayerResult[CaptureData]:
    payload, values = await read_upload(request)
    hint = document_hint(values)
    return await run_in_threadpool(lambda: preprocess(decode_image(payload), hint))


@router.post(
    "/ocr/extract",
    response_model=LayerResult[OCRData],
    openapi_extra=upload_schema(),
    tags=["L1"],
)
async def ocr(request: Request) -> LayerResult[OCRData]:
    payload, values = await read_upload(request)
    hint = document_hint(values)
    return await run_in_threadpool(lambda: extract_ocr(decode_image(payload), hint))


@router.post("/ocr/parse-mrz", response_model=MRZData, tags=["L1"])
def parse(request: MRZRequest) -> MRZData:
    return parse_mrz(request.lines)


@router.post(
    "/validation/check", response_model=LayerResult[ValidationData], tags=["L2"]
)
def validation(request: ValidationRequest) -> LayerResult[ValidationData]:
    return validate_document(request)


@router.post(
    "/phase1/analyze",
    response_model=Phase1Result,
    openapi_extra=upload_schema(reference_date=True),
    tags=["Phase 1"],
)
async def phase1(request: Request) -> Phase1Result:
    payload, values = await read_upload(request)
    try:
        reference = date.fromisoformat(values["reference_date"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            422, "reference_date must be supplied as YYYY-MM-DD."
        ) from exc
    hint = document_hint(values)
    return await run_in_threadpool(analyze_phase1, payload, reference, hint)
