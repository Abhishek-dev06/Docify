"""Bounded risk inputs and explicit incomplete-evidence outputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SignalName = Literal[
    "blacklist",
    "duplicate_identity",
    "face",
    "mrz",
    "cross_fields",
    "dates",
    "tampering",
    "liveness",
    "metadata",
    "format",
]


class RiskSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    value: float | None = Field(default=None, ge=0, le=1)
    complete: bool = False
    explanation: str = Field(min_length=1, max_length=1000)
    source: str = Field(min_length=1, max_length=100)
    experimental: bool = False


class RiskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signals: dict[SignalName, RiskSignal] = Field(default_factory=dict)


class RiskContribution(BaseModel):
    name: SignalName
    weight: float
    value: float | None
    points: float
    complete: bool
    explanation: str
    source: str
    experimental: bool


class RiskData(BaseModel):
    score: float | None = Field(ge=0, le=100)
    category: Literal["Low", "Medium", "High"] | None
    score_range: tuple[float, float]
    evidence_coverage: float = Field(ge=0, le=1)
    missing_signals: list[SignalName]
    missing_required_signals: list[SignalName]
    contributions: list[RiskContribution]
    reasons: list[str]
    policy_version: str
    policy_sha256: str
    engine: str = "transparent-weighted-v1"
    calibrated: bool = False
    human_review_required: bool = True
    automatic_decision: None = None
    scope: str = "synthetic-development-demo"
    evidence_origin: Literal["caller_supplied", "server_layers"] = "caller_supplied"
