"""L5 uncertainty, arithmetic, policy invariants and evidence translation."""

from copy import deepcopy

import pytest
from app.layers.l2_validation.checks import validate_document
from app.layers.l5_risk.engine import RiskPolicy, WeightedRiskEngine, score_risk
from app.layers.l5_risk.evidence import risk_inputs
from app.schemas.common import LayerResult
from app.schemas.faces import LivenessData, VerificationData
from app.schemas.risk import RiskInput, RiskSignal
from app.schemas.tampering import DetectorEvidence, TamperingData
from app.settings import load_config
from pydantic import ValidationError


def signal(value=0.0, complete=True):
    return RiskSignal(
        value=value,
        complete=complete,
        explanation="Controlled test evidence.",
        source="test",
    )


def complete_inputs(**overrides):
    values = {n: signal() for n in load_config("risk_weights.yaml")["weights"]}
    values.update({n: signal(v) for n, v in overrides.items()})
    return RiskInput(signals=values)


def test_unknown_never_gets_zero_score_or_low_category():
    result = score_risk(RiskInput())
    assert result.status == "insufficient_evidence"
    assert result.data.score is None and result.data.category is None
    assert result.data.score_range == (0.0, 100.0)
    assert result.data.evidence_coverage == 0


def test_complete_low_evidence_does_not_approve():
    data = score_risk(complete_inputs()).data
    assert data.score == 0 and data.category == "Low"
    assert data.score_range == (0, 0) and data.evidence_coverage == 1
    assert data.human_review_required and data.automatic_decision is None


@pytest.mark.parametrize(
    "values,score,category",
    [
        ({"mrz": 1}, 8, "Low"),
        ({"face": 1}, 15, "Medium"),
        ({"blacklist": 1}, 35, "High"),
        (
            {
                "blacklist": 1,
                "duplicate_identity": 1,
                "face": 1,
                "mrz": 1,
                "cross_fields": 1,
                "dates": 1,
                "tampering": 1,
                "liveness": 1,
                "metadata": 1,
                "format": 1,
            },
            100,
            "High",
        ),
    ],
)
def test_exact_weights_and_inclusive_boundaries(values, score, category):
    data = score_risk(complete_inputs(**values)).data
    assert data.score == score and data.category == category
    assert sum(c.points for c in data.contributions) == score


def test_known_high_survives_missing_evidence():
    result = score_risk(RiskInput(signals={"blacklist": signal(1)}))
    assert result.status == "insufficient_evidence"
    assert result.data.category == "High" and result.data.score == 35
    assert result.data.score_range == (35, 100)


def test_missing_required_suppresses_low_and_preserves_upper_bound():
    inputs = complete_inputs()
    inputs.signals["face"] = signal(None, False)
    data = score_risk(inputs).data
    assert data.category is None and data.score_range == (0, 15)
    assert data.evidence_coverage == 0.85
    assert data.missing_required_signals == ["face"]


def test_partial_positive_signal_is_not_treated_as_complete():
    inputs = complete_inputs()
    inputs.signals["tampering"] = signal(0.3, False)
    data = score_risk(inputs).data
    assert data.score == 1.5 and data.score_range == (1.5, 5)
    assert data.category is None


def test_claimed_complete_null_remains_unknown():
    data = score_risk(RiskInput(signals={"face": signal(None, True)})).data
    assert "face" in data.missing_required_signals
    assert data.score is None


@pytest.mark.parametrize("value", [-0.1, 1.01, float("nan"), float("inf")])
def test_invalid_signal_rejected(value):
    with pytest.raises(ValidationError):
        signal(value)


@pytest.mark.parametrize(
    "mutation", ["sum", "negative", "nan", "threshold", "missing", "required"]
)
def test_invalid_policy_rejected(mutation):
    cfg = deepcopy(load_config("risk_weights.yaml"))
    if mutation == "sum":
        cfg["weights"]["blacklist"] = 34
    elif mutation == "negative":
        cfg["weights"]["metadata"] = -2
    elif mutation == "nan":
        cfg["weights"]["metadata"] = float("nan")
    elif mutation == "threshold":
        cfg["medium_threshold"] = 36
    elif mutation == "missing":
        del cfg["weights"]["metadata"]
    else:
        cfg["required_signals"] = []
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(cfg)


def test_policy_hash_is_stable_and_changes_with_weights():
    a = WeightedRiskEngine()
    cfg = load_config("risk_weights.yaml")
    cfg["weights"]["mrz"] += 1
    cfg["weights"]["metadata"] -= 1
    b = WeightedRiskEngine(RiskPolicy.model_validate(cfg))
    assert a.digest == WeightedRiskEngine().digest != b.digest


def test_l2_adapter_ignores_fabricated_mismatch_counter(validation_request, db_url):
    result = validate_document(validation_request, db_url)
    result.data.mismatch_count = 999
    inputs = risk_inputs(validation=result)
    assert inputs.signals["cross_fields"].value == 0
    assert inputs.signals["blacklist"].value == 0
    assert inputs.signals["mrz"].value == 0


def test_multiple_checksum_failures_are_capped(validation_request, db_url):
    result = validate_document(validation_request, db_url)
    for check in result.data.checks:
        check.valid = False
    inputs = risk_inputs(validation=result)
    data = score_risk(inputs).data
    assert next(c.points for c in data.contributions if c.name == "mrz") == 8


def test_unavailable_database_overrides_false_hit(validation_request, db_url):
    result = validate_document(validation_request, db_url)
    result.data.database_available = False
    result.data.blacklist_hit = False
    assert risk_inputs(validation=result).signals["blacklist"].value is None


def test_previous_sightings_do_not_raise_risk(validation_request, db_url):
    result = validate_document(validation_request, db_url)
    before = score_risk(risk_inputs(validation=result)).data.score
    result.data.previously_seen = 500
    assert score_risk(risk_inputs(validation=result)).data.score == before


def test_tamper_metadata_not_counted_twice_and_cnn_excluded():
    detectors = [
        DetectorEvidence(name=n, score=s, method="test", explanation="Test")
        for n, s in [
            ("metadata", 1),
            ("cnn", 1),
            ("noise_splicing", 0.2),
            ("photo_replacement", 0.1),
            ("copy_move", 0),
            ("font_inconsistency", 0),
        ]
    ]
    result = LayerResult(
        data=TamperingData(
            detectors=detectors,
            suspicion_score=1,
            heatmap_png_base64="",
            overlay_png_base64="",
            width=1,
            height=1,
            limitations=[],
        )
    )
    inputs = risk_inputs(tampering=result)
    assert inputs.signals["tampering"].value == 0.2
    assert inputs.signals["metadata"].value == 1
    assert inputs.signals["tampering"].experimental


def test_inconclusive_liveness_never_becomes_complete_zero():
    result = LayerResult(data=LivenessData(spoof_indicator_score=0))
    signal_value = risk_inputs(liveness=result).signals["liveness"]
    assert signal_value.value is None and not signal_value.complete


def test_suspicious_liveness_retains_points_and_uncertainty():
    result = LayerResult(
        data=LivenessData(spoof_indicator_score=0.5, verdict="suspicious")
    )
    data = score_risk(risk_inputs(liveness=result)).data
    assert data.score == 2 and "liveness" in data.missing_required_signals


def test_face_adapter_recomputes_decision_from_similarity():
    result = LayerResult(
        data=VerificationData(
            cosine_similarity=0.4,
            threshold=0.6,
            match=True,
            decision="match",
            document_face_count=1,
            live_face_count=1,
        )
    )
    assert risk_inputs(face=result).signals["face"].value == 1
    result.status = "unavailable"
    assert "face" not in risk_inputs(face=result).signals
