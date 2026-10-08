"""Heuristic liveness tests deliberately do not claim PAD accuracy."""

import numpy as np
import pytest
from app.layers.l4_face.liveness import (
    blink_candidate,
    evaluate_liveness,
    texture_features,
)
from app.schemas.faces import FrameEvidence
from app.settings import load_config
from test_faces import FakeFaceEngine, unit_image


def observations(eyes):
    return [
        FrameEvidence(
            index=i,
            timestamp_ms=i * 100,
            face_count=1,
            eyes_visible=count,
            quality_ok=True,
            same_face_as_first=True,
        )
        for i, count in enumerate(eyes)
    ]


def test_blink_candidate_requires_ordered_open_closed_open():
    cfg = load_config("face_thresholds.yaml")
    assert blink_candidate(observations([2, 2, 0, 2, 2]), cfg)
    assert not blink_candidate(observations([2, 2, 2, 2, 2]), cfg)
    assert not blink_candidate(observations([2, 2, 1, 2, 2]), cfg)
    assert not blink_candidate(observations([0, 0, 2, 2, 2]), cfg)


def test_tracking_failure_invalidates_blink_candidate():
    evidence = observations([2, 2, 0, 2, 2])
    evidence[2].same_face_as_first = False
    assert not blink_candidate(evidence, load_config("face_thresholds.yaml"))


def test_sparse_sequence_does_not_imply_blink():
    evidence = observations([2, 2, 0, 2, 2])
    evidence[-1].timestamp_ms = 2000
    assert not blink_candidate(evidence, load_config("face_thresholds.yaml"))


@pytest.mark.parametrize(
    "times", [None, [0, 0], [1, 0], [0, float("nan")], [0], [0, 25000]]
)
def test_invalid_sequence_timing_is_rejected(times):
    with pytest.raises(ValueError):
        evaluate_liveness([unit_image(), unit_image()], times, FakeFaceEngine())


def test_single_frame_never_certifies_liveness(monkeypatch):
    monkeypatch.setattr(
        "app.layers.l4_face.liveness.visible_eyes", lambda image, row: 2
    )
    result = evaluate_liveness([unit_image()], engine=FakeFaceEngine())
    assert result.status == "insufficient_evidence"
    assert result.data.liveness_score is None
    assert result.data.review_required
    assert not result.data.blink_candidate


def test_identical_frames_flag_replay_evidence(monkeypatch):
    monkeypatch.setattr(
        "app.layers.l4_face.liveness.visible_eyes", lambda image, row: 2
    )
    result = evaluate_liveness(
        [unit_image()] * 5, [0, 100, 200, 300, 400], FakeFaceEngine()
    )
    assert result.data.repeated_frame_count == 4
    assert result.data.verdict == "suspicious"
    assert result.data.liveness_score is None


def test_blink_candidate_still_is_not_live_verdict(monkeypatch):
    eyes = iter([2, 2, 0, 2, 2])
    monkeypatch.setattr(
        "app.layers.l4_face.liveness.visible_eyes", lambda image, row: next(eyes)
    )
    result = evaluate_liveness(
        [unit_image(i) for i in range(5)], [0, 100, 200, 300, 400], FakeFaceEngine()
    )
    assert result.data.blink_candidate
    assert result.data.liveness_score is None
    assert result.data.verdict == "inconclusive"


def test_texture_statistics_detect_periodic_pattern_without_probability_claim():
    stripe = (127 + 100 * np.sin(np.arange(128) * 2 * np.pi / 4)).astype(np.uint8)
    image = np.tile(stripe[None, :, None], (128, 1, 3))
    contrast, periodic = texture_features(image)
    assert contrast > 50 and periodic > 0.45
    assert texture_features(np.full((128, 128, 3), 120, np.uint8)) == (0, 0)


def test_liveness_missing_model_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("FACE_MODEL_DIR", str(tmp_path))
    result = evaluate_liveness([unit_image()])
    assert result.status == "unavailable"
    assert result.data.liveness_score is None
