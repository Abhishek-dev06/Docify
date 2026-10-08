"""Deterministic points, coverage and missing-evidence bounds."""

import hashlib
import json
import time
from typing import Protocol, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import LayerResult
from app.schemas.risk import (
    RiskContribution,
    RiskData,
    RiskInput,
    RiskSignal,
    SignalName,
)
from app.settings import load_config


class RiskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: str = Field(min_length=1)
    medium_threshold: float = Field(gt=0, le=100)
    high_threshold: float = Field(gt=0, le=100)
    weights: dict[SignalName, float]
    required_signals: list[SignalName]

    @model_validator(mode="after")
    def validate_policy(self):
        if set(self.weights) != set(get_args(SignalName)):
            raise ValueError("Policy must explicitly configure every signal.")
        if any(w < 0 or w > 100 for w in self.weights.values()):
            raise ValueError("Weights must be between zero and 100.")
        if abs(sum(self.weights.values()) - 100) > 1e-8:
            raise ValueError("Policy weights must sum to 100.")
        if self.medium_threshold >= self.high_threshold:
            raise ValueError("Medium threshold must be below High.")
        if (
            not self.required_signals
            or len(set(self.required_signals)) != len(self.required_signals)
            or any(self.weights[n] <= 0 for n in self.required_signals)
        ):
            raise ValueError(
                "Required signals must be unique and have positive weights."
            )
        return self


class RiskEngine(Protocol):
    """Future learned engines must retain this explanation/coverage contract."""

    def score(self, inputs: RiskInput) -> LayerResult[RiskData]: ...


class WeightedRiskEngine:
    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self.policy = policy or RiskPolicy.model_validate(
            load_config("risk_weights.yaml")
        )
        canonical = json.dumps(
            self.policy.model_dump(), sort_keys=True, separators=(",", ":")
        )
        self.digest = hashlib.sha256(canonical.encode()).hexdigest()

    def score(self, inputs: RiskInput) -> LayerResult[RiskData]:
        started = time.perf_counter()
        items, missing, reasons = [], [], []
        lower, upper, covered, observed = 0.0, 0.0, 0.0, False
        for name, weight in self.policy.weights.items():
            signal = inputs.signals.get(
                name,
                RiskSignal(
                    explanation="No usable evidence supplied.", source="missing"
                ),
            )
            complete = signal.complete and signal.value is not None
            points = round(weight * (signal.value or 0), 4)
            lower += points
            upper += points if complete else weight
            observed |= weight > 0 and signal.value is not None
            if complete:
                covered += weight
            elif weight > 0:
                missing.append(name)
            items.append(
                RiskContribution(
                    name=name,
                    weight=weight,
                    value=signal.value,
                    points=round(points, 4),
                    complete=complete,
                    explanation=signal.explanation,
                    source=signal.source,
                    experimental=signal.experimental,
                )
            )
            if points > 0:
                reasons.append(
                    f"{name}: +{points:.2f}/{weight:g} points. {signal.explanation}"
                )
        lower = round(lower, 4)
        required_missing = [n for n in missing if n in self.policy.required_signals]
        category = None
        if observed:
            if lower >= self.policy.high_threshold:
                category = "High"
            elif not required_missing:
                category = "Medium" if lower >= self.policy.medium_threshold else "Low"
        if required_missing:
            reasons.append(
                "Required evidence incomplete: "
                + ", ".join(required_missing)
                + ". Missing evidence is not a clean result."
            )
        if not reasons:
            reasons.append(
                "No positive signals in supplied evidence; human review still required."
            )
        data = RiskData(
            score=round(lower, 4) if observed else None,
            category=category,
            score_range=(round(lower, 4), round(upper, 4)),
            evidence_coverage=round(covered / 100, 4),
            missing_signals=missing,
            missing_required_signals=required_missing,
            contributions=items,
            reasons=reasons,
            policy_version=self.policy.version,
            policy_sha256=self.digest,
        )
        return LayerResult(
            status="insufficient_evidence" if required_missing else "ok",
            data=data,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )


def score_risk(inputs: RiskInput) -> LayerResult[RiskData]:
    return WeightedRiskEngine().score(inputs)
