import numpy as np
import pytest
from app.evaluation import binary_metrics, latency_summary, mask_iou, roc_points


def test_known_confusion_and_undefined_denominators():
    m = binary_metrics([True, True, False, False], [True, False, True, False])
    assert m["confusion_matrix"] == {"tp": 1, "fn": 1, "fp": 1, "tn": 1}
    assert m["precision"] == m["recall"] == m["f1"] == 0.5
    assert binary_metrics([], [])["precision"] is None
    assert binary_metrics([True], [False])["precision"] is None
    with pytest.raises(ValueError):
        binary_metrics([True], [])


def test_roc_ties_and_threshold_equality():
    points = roc_points([True, False, True, False], [0.9, 0.9, 0.5, 0.1])
    assert points[1] == {"threshold": 0.9, "fpr": 0.5, "tpr": 0.5}
    assert points[-1]["fpr"] == points[-1]["tpr"] == 1
    assert roc_points([True], [0.9]) == []
    with pytest.raises(ValueError):
        roc_points([True], [float("nan")])


def test_iou_empty_and_known_overlap():
    assert mask_iou(np.array([1, 1, 0]), np.array([0, 1, 1])) == 1 / 3
    assert mask_iou(np.zeros((2, 2)), np.zeros((2, 2))) is None
    with pytest.raises(ValueError):
        mask_iou(np.zeros((2, 2)), np.zeros((2, 3)))


def test_latency_is_descriptive_and_counts_samples():
    summary = latency_summary([100, 200, 300])
    assert summary["n"] == 3
    assert summary["median_ms"] == 200
    assert summary["p95_ms"] == 290
    with pytest.raises(ValueError):
        latency_summary([])
