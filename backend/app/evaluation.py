"""Auditable evaluation primitives; undefined ratios remain null."""

import math

import numpy as np


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def binary_metrics(truth: list[bool], predicted: list[bool]) -> dict:
    if len(truth) != len(predicted):
        raise ValueError("Prediction and truth lengths differ.")
    pairs = list(zip(truth, predicted, strict=True))
    tp = sum(bool(a) and bool(b) for a, b in pairs)
    fp = sum(not a and bool(b) for a, b in pairs)
    fn = sum(bool(a) and not b for a, b in pairs)
    tn = sum(not a and not b for a, b in pairs)
    return {
        "n": len(pairs),
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "false_positive_rate": ratio(fp, fp + tn),
        "false_negative_rate": ratio(fn, fn + tp),
    }


def roc_points(truth: list[bool], scores: list[float]) -> list[dict]:
    if len(truth) != len(scores) or not all(math.isfinite(s) for s in scores):
        raise ValueError("ROC requires aligned finite scores.")
    if not any(truth) or all(truth):
        return []
    points = [{"threshold": None, "fpr": 0.0, "tpr": 0.0}]
    for threshold in sorted(set(scores), reverse=True):
        metrics = binary_metrics(truth, [s >= threshold for s in scores])
        points.append(
            {
                "threshold": threshold,
                "fpr": metrics["false_positive_rate"],
                "tpr": metrics["recall"],
            }
        )
    return points


def mask_iou(truth: np.ndarray, predicted: np.ndarray) -> float | None:
    if truth.shape != predicted.shape:
        raise ValueError("Mask dimensions differ.")
    a, b = truth.astype(bool), predicted.astype(bool)
    return ratio(int((a & b).sum()), int((a | b).sum()))


def latency_summary(milliseconds: list[float]) -> dict:
    if not milliseconds or any(not math.isfinite(t) or t < 0 for t in milliseconds):
        raise ValueError("Latency samples must be nonempty, finite and nonnegative.")
    return {
        "n": len(milliseconds),
        "mean_ms": float(np.mean(milliseconds)),
        "median_ms": float(np.median(milliseconds)),
        "p95_ms": float(np.percentile(milliseconds, 95, method="linear")),
        "min_ms": min(milliseconds),
        "max_ms": max(milliseconds),
        "p95_method": "linear interpolation; descriptive only for small samples",
    }
