"""Explicit availability and provenance for uncalibrated L3 evidence."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Finding


class DetectorEvidence(BaseModel):
    name: str
    status: Literal["ok", "insufficient_evidence", "unavailable"] = "ok"
    score: float | None = Field(default=None, ge=0, le=1)
    method: str
    explanation: str
    regions: list[tuple[float, float, float, float]] = Field(default_factory=list)
    metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)


class TamperingData(BaseModel):
    suspicion_score: float | None = Field(default=None, ge=0, le=1)
    tamper_probability: float | None = None
    score_calibrated: bool = False
    detectors: list[DetectorEvidence]
    heatmap_png_base64: str
    overlay_png_base64: str
    width: int
    height: int
    coordinate_frame: str = "EXIF-oriented original, resized; normalized xywh"
    heatmap_source: str = "maximum of available localized classical signals"
    cnn_heatmap_png_base64: str | None = None
    limitations: list[str]


def finding(evidence: DetectorEvidence) -> Finding:
    return Finding(
        code="TAMPER_" + evidence.name.upper(),
        severity="medium" if (evidence.score or 0) >= 0.55 else "info",
        explanation=evidence.explanation,
        region=evidence.regions[0] if evidence.regions else None,
    )
