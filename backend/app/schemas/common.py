"""Shared, validated response models."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

Status = Literal["ok", "needs_rescan", "insufficient_evidence", "unavailable"]
DocumentType = Literal["passport", "visa", "id", "license", "permit", "unknown"]
T = TypeVar("T")


class Finding(BaseModel):
    code: str
    severity: Literal["info", "low", "medium", "high"] = "info"
    explanation: str
    field: str | None = None
    region: tuple[float, float, float, float] | None = None


class LayerResult(BaseModel, Generic[T]):
    status: Status = "ok"
    data: T
    findings: list[Finding] = Field(default_factory=list)
    duration_ms: float = 0


class FieldValue(BaseModel):
    raw: str | None = None
    corrected: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Literal["mrz", "viz"]
    corrections: list[str] = Field(default_factory=list)
