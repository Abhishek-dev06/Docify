"""Deterministic unit tests and real-model synthetic smoke tests are separate."""

import math
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest
from app.layers.l4_face.engine import (
    ModelUnavailable,
    OpenCVFaceEngine,
    cosine_similarity,
    get_engine,
    normalize_embedding,
)
from app.layers.l4_face.synthetic_identity_index import synthetic_portrait
from app.layers.l4_face.verification import detect_faces, verify_faces
from app.schemas.faces import FaceObservation
from app.settings import ROOT, load_config


class FakeFaceEngine:
    """Controlled evidence for control-flow tests; not biometric evaluation."""

    model_sha256 = "unit-test-engine"

    def detect(self, image):
        code = int(image[0, 0, 0])
        count = 0 if code == 255 else 2 if code == 254 else 1
        good = code != 253
        observation = FaceObservation(
            box=(0.2, 0.2, 0.6, 0.6),
            landmarks=[(0.4, 0.4)] * 5,
            detection_confidence=0.99,
            width_pixels=100,
            height_pixels=100,
            laplacian_variance=100 if good else 1,
            brightness=120,
            quality_ok=good,
            quality_reasons=[] if good else ["FACE_BLURRED"],
        )
        row = np.array([20, 20, 60, 60] + [40, 40] * 5 + [0.99], dtype=np.float32)
        return [observation] * count, [row] * count

    def embedding(self, image, row):
        return np.array(
            [0, 1] if int(image[0, 0, 0]) == 100 else [1, 0], dtype=np.float32
        )


def unit_image(code=0):
    image = np.random.default_rng(19).integers(30, 220, (100, 100, 3), dtype=np.uint8)
    image[0, 0, 0] = code
    return image


def test_cosine_is_scale_invariant_and_bounded():
    assert cosine_similarity(np.array([1, 2]), np.array([3, 6])) == pytest.approx(1)
    assert cosine_similarity(np.array([1, 0]), np.array([-1, 0])) == -1
    assert cosine_similarity(np.array([1, 0]), np.array([0, 1])) == 0


@pytest.mark.parametrize("vector", [[], [0, 0], [math.nan, 1], [math.inf, 1]])
def test_invalid_embeddings_are_not_scores(vector):
    with pytest.raises(ValueError):
        normalize_embedding(np.array(vector))


def test_incompatible_embedding_dimensions():
    with pytest.raises(ValueError):
        cosine_similarity(np.ones(2), np.ones(3))


@pytest.mark.parametrize("threshold", [math.nan, math.inf, -1.1, 1.1])
def test_bad_threshold_rejected(threshold):
    with pytest.raises(ValueError):
        verify_faces(unit_image(), unit_image(), threshold, FakeFaceEngine())


@pytest.mark.parametrize(
    "code,reason", [(255, "NO_FACE"), (254, "MULTIPLE_FACES"), (253, "FACE_QUALITY")]
)
def test_bad_evidence_abstains(code, reason):
    result = verify_faces(unit_image(), unit_image(code), engine=FakeFaceEngine())
    assert result.status == "insufficient_evidence"
    assert result.data.match is None and result.data.cosine_similarity is None
    assert result.data.decision == "undetermined"
    assert reason in {f.code for f in result.findings}


def test_threshold_boundary_and_non_match_are_explicit():
    match = verify_faces(unit_image(), unit_image(), 1.0, FakeFaceEngine())
    assert match.data.match is True
    mismatch = verify_faces(unit_image(), unit_image(100), 0.5, FakeFaceEngine())
    assert mismatch.status == "ok"
    assert mismatch.data.match is False
    assert mismatch.data.decision == "non_match"
    assert mismatch.data.liveness_verified is False
    assert "embedding" not in mismatch.model_dump_json()


def test_missing_models_report_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("FACE_MODEL_DIR", str(tmp_path))
    result = verify_faces(unit_image(), unit_image())
    assert result.status == "unavailable"
    assert result.data.match is None


def test_modified_model_is_rejected_before_loading(tmp_path):
    (tmp_path / "face_detection_yunet_2023mar.onnx").write_bytes(b"not a model")
    with pytest.raises(ModelUnavailable, match="Integrity"):
        OpenCVFaceEngine(tmp_path, load_config("face_thresholds.yaml"))


def test_non_uint8_input_is_rejected():
    with pytest.raises(ValueError):
        detect_faces(np.zeros((30, 30, 3), dtype=np.float32))


models_present = all(
    (ROOT / "models" / name).is_file()
    for name in [
        "face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx",
    ]
)


@pytest.mark.face_models
@pytest.mark.skipif(not models_present, reason="Face models not downloaded")
def test_real_models_on_generated_portraits():
    a, b = synthetic_portrait("synthetic_a"), synthetic_portrait("synthetic_b")
    transformed = cv2.convertScaleAbs(cv2.resize(a, (600, 600)), alpha=0.95, beta=7)
    positive = verify_faces(a, transformed)
    negative = verify_faces(a, b)
    assert positive.status == negative.status == "ok"
    assert positive.data.match is True
    assert negative.data.match is False
    assert positive.data.cosine_similarity > negative.data.cosine_similarity
    features = get_engine().embedding(a, get_engine().detect(a)[1][0])
    assert features.shape == (128,)
    assert np.linalg.norm(features) == pytest.approx(1)


@pytest.mark.face_models
@pytest.mark.skipif(not models_present, reason="Face models not downloaded")
def test_real_no_face_and_multiple_faces():
    a, b = synthetic_portrait("synthetic_a"), synthetic_portrait("synthetic_b")
    blank = np.full((500, 500, 3), 180, np.uint8)
    multiple = np.concatenate(
        [cv2.resize(a, (500, 500)), cv2.resize(b, (500, 500))], axis=1
    )
    assert verify_faces(a, blank).data.match is None
    result = verify_faces(a, multiple)
    assert result.data.live_face_count == 2 and result.data.match is None


@pytest.mark.face_models
@pytest.mark.skipif(not models_present, reason="Face models not downloaded")
def test_shared_model_is_safe_for_concurrent_comparisons():
    a, b = synthetic_portrait("synthetic_a"), synthetic_portrait("synthetic_b")
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(verify_faces, a, image) for image in [a, b, a, b]]
    assert [task.result().data.match for task in tasks] == [True, False, True, False]
