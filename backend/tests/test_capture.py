"""Geometry and quality gates on generated images."""

import cv2
import numpy as np
import pytest
from app.demo import generate_document
from app.layers.l0_capture.preprocess import decode_image, preprocess


def test_crisp_synthetic_document_passes():
    payload, _ = generate_document()
    result = preprocess(decode_image(payload))
    assert result.status == "ok"
    assert result.data.quality.width > 1000


def test_perspective_correction_finds_document():
    payload, _ = generate_document(variant="perspective")
    result = preprocess(decode_image(payload))
    assert result.data.boundary_detected
    assert result.status == "ok"
    assert not np.allclose(result.data.transform, np.eye(3))


@pytest.mark.parametrize("value,code", [(0, "DARK"), (255, "POSSIBLE_GLARE")])
def test_bad_lighting(value, code):
    result = preprocess(np.full((700, 1100, 3), value, dtype=np.uint8))
    assert result.status == "needs_rescan"
    assert code in {f.code for f in result.findings}


def test_blur_requires_rescan():
    payload, _ = generate_document(variant="blurred")
    result = preprocess(decode_image(payload))
    assert result.status == "needs_rescan"
    assert "BLUR" in {f.code for f in result.findings}


def test_small_image_requires_rescan():
    payload, _ = generate_document()
    image = cv2.resize(decode_image(payload), (320, 200))
    result = preprocess(image)
    assert "LOW_RESOLUTION" in {f.code for f in result.findings}


@pytest.mark.parametrize(
    "payload",
    [b"", b"not an image", b"x" * (10 * 1024 * 1024 + 1)],
    ids=["empty", "invalid", "oversized"],
)
def test_invalid_or_large_upload_rejected(payload):
    with pytest.raises(ValueError):
        decode_image(payload)
