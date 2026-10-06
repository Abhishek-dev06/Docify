"""Structured document evidence. MRZ dates retain YYMMDD until validation."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import DocumentType, FieldValue


class Quality(BaseModel):
    width: int
    height: int
    laplacian_variance: float
    brightness: float
    saturated_fraction: float


class CaptureData(BaseModel):
    document_type: DocumentType
    classification_confidence: float | None = None
    classification_method: str
    boundary_detected: bool
    quality: Quality
    image_base64: str
    mime_type: str = "image/png"
    transform: list[list[float]]


class CheckDigit(BaseModel):
    field: str
    input: str
    observed: str
    expected: str | None
    valid: bool | None


class MRZData(BaseModel):
    format: Literal["TD1", "TD2", "TD3"]
    raw_lines: list[str]
    corrected_lines: list[str]
    fields: dict[str, FieldValue]
    checks: list[CheckDigit]
    corrections: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class OCRData(BaseModel):
    document_type: DocumentType = "unknown"
    raw_text: str = ""
    mrz: MRZData | None = None
    viz_fields: dict[str, FieldValue] = Field(default_factory=dict)
    engine: str = "tesseract"


class ValidationRequest(BaseModel):
    document_type: DocumentType = "unknown"
    reference_date: date
    mrz: MRZData | None = None
    viz_fields: dict[str, FieldValue] = Field(default_factory=dict)


class CrossCheck(BaseModel):
    field: str
    mrz_value: str | None
    viz_value: str | None
    consistent: bool | None


class ValidationData(BaseModel):
    checks: list[CheckDigit]
    cross_checks: list[CrossCheck]
    mismatch_count: int
    resolved_dates: dict[str, str | None]
    blacklist_hit: bool | None
    previously_seen: int | None
    database_available: bool
