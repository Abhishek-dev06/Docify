"""L3 signal semantics, coordinate frames, malformed inputs and optional models."""

import base64
import hashlib
import json
from io import BytesIO

import cv2
import numpy as np
import pytest
from app.layers.l3_tampering.analyzer import analyze_tampering, overlay
from app.layers.l3_tampering.classical import (
    compression,
    ela,
    metadata,
    photo,
    regions_from_map,
    validate_region,
)
from app.layers.l3_tampering.learned import predict
from app.layers.l3_tampering.stamps import compare_template, decode_yolo, demo_template
from app.layers.l3_tampering.synthetic import ATTACKS, make_variant, split_group
from app.main import app
from app.settings import ROOT
from fastapi.testclient import TestClient
from PIL import Image


def payload(image, extension=".png"):
    return cv2.imencode(extension, image)[1].tobytes()


def test_metadata_absence_is_unknown():
    evidence = metadata(payload(np.full((64, 64, 3), 128, np.uint8)))
    assert evidence.status == "insufficient_evidence" and evidence.score is None


def test_metadata_editor_and_reversed_dates():
    exif = Image.Exif()
    exif[305] = "Adobe Photoshop"
    exif[306] = "2020:01:01 12:00:00"
    exif[36867] = "2021:01:01 12:00:00"
    stream = BytesIO()
    Image.new("RGB", (64, 64)).save(stream, "JPEG", exif=exif)
    result = metadata(stream.getvalue())
    assert result.score == 1
    assert result.metrics["reversed_timestamps"] is True
    assert "Photoshop" not in result.model_dump_json()


def test_lossless_input_has_no_compression_verdict():
    image, _ = make_variant(1, "clean")
    assert compression(image, False).score is None
    evidence, heat = ela(image, False)
    assert evidence.status == "unavailable" and not heat.any()


def test_ela_localizes_recompression_error_without_auto_scaling():
    image = np.full((192, 192, 3), 120, np.uint8)
    image[70:110, 60:100] = np.random.default_rng(1).integers(0, 256, (40, 40, 3))
    evidence, heat = ela(image, True)
    assert heat[70:110, 60:100].mean() > heat[:40].mean() + 0.3
    assert evidence.regions
    assert not ela(np.full_like(image, 128), True)[1].any()


@pytest.mark.parametrize(
    "region",
    [
        [-0.1, 0, 0.2, 0.2],
        [0, 0, 0, 0.1],
        [0.9, 0, 0.2, 0.1],
        [0, 0, float("nan"), 0.2],
        [0, 0, float("inf"), 0.2],
        [1],
        None,
        {},
        [[], 0, 0.1, 0.1],
        [None, 0, 0.1, 0.1],
    ],
)
def test_bad_photo_regions_rejected(region):
    with pytest.raises(ValueError):
        validate_region(region)


def test_photo_absent_or_no_surroundings_are_unknown():
    image, _ = make_variant(1, "clean")
    assert photo(image, None)[0].score is None
    assert photo(image, (0, 0, 1, 1))[0].status == "insufficient_evidence"


def test_heatmap_regions_and_overlay_preserve_geometry():
    heat = np.zeros((100, 200), np.float32)
    heat[20:50, 100:150] = 1
    assert regions_from_map(heat) == [(0.5, 0.2, 0.25, 0.3)]
    image = np.full((100, 200, 3), 120, np.uint8)
    marked = overlay(image, heat)
    assert np.array_equal(marked[:20], image[:20])
    assert not np.array_equal(marked[20:50, 100:150], image[20:50, 100:150])


def test_missing_cnn_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("TAMPER_MODEL_PATH", str(tmp_path / "absent.pt"))
    result, heat = predict(np.zeros((192, 192, 3), np.uint8))
    assert result.score is None and result.status == "unavailable" and heat is None


def test_corrupt_cnn_is_unavailable(tmp_path, monkeypatch):
    checkpoint = tmp_path / "bad.pt"
    checkpoint.write_bytes(b"invalid")
    checkpoint.with_suffix(".json").write_text(
        json.dumps(
            {
                "architecture": "tiny-unet-v1",
                "input_size": 192,
                "training_domain": "procedural-synthetic-v1",
                "sha256": "0" * 64,
            }
        )
    )
    monkeypatch.setenv("TAMPER_MODEL_PATH", str(checkpoint))
    assert predict(np.zeros((192, 192, 3), np.uint8))[0].status == "unavailable"


def test_stamp_same_template_matches_without_authenticity_claim():
    assert compare_template(demo_template(), demo_template()) > 0.99


def test_yolo_letterbox_coordinates_and_nms():
    # 200x100 image -> scale 3.2, vertical padding 160.
    raw = np.asarray(
        [[[320, 320], [320, 320], [160, 160], [160, 160], [0.9, 0.8]]], dtype=np.float32
    )
    assert decode_yolo(raw, (100, 200, 3)) == [(75, 25, 50, 50)]
    with pytest.raises(ValueError):
        decode_yolo(np.zeros((1, 84, 8400)), (100, 200, 3))


def test_generator_masks_and_source_split():
    group = "same-source"
    assert all(split_group(group) == split_group(group) for _ in ATTACKS)
    for attack in ATTACKS:
        image, mask = make_variant(9, attack)
        assert image.shape[:2] == mask.shape
        assert bool(mask.any()) == (attack != "clean")
        assert np.array_equal(make_variant(9, attack)[0], image)


def test_rest_response_and_no_probability(monkeypatch):
    monkeypatch.delenv("STAMP_YOLO_PATH", raising=False)
    image, _ = make_variant(8, "text_replacement")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tampering/analyze",
            files={"document": ("demo.jpg", payload(image, ".jpg"), "image/jpeg")},
            data={"include_cnn": "false", "photo_region": "[0.66,0.16,0.27,0.45]"},
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tamper_probability"] is None and not data["score_calibrated"]
    decoded = cv2.imdecode(
        np.frombuffer(base64.b64decode(data["heatmap_png_base64"]), dtype=np.uint8),
        cv2.IMREAD_GRAYSCALE,
    )
    assert decoded.shape == image.shape[:2]
    detectors = {e["name"]: e for e in data["detectors"]}
    assert detectors["stamp_yolo"]["status"] == "unavailable"
    assert detectors["stamp_template"]["score"] is None
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "data",
    [
        {"photo_region": "null"},
        {"include_cnn": "yes"},
        {"photo_region": "[null,0,0.1,0.1]"},
        {"photo_region": "{}"},
        {"bad": "x"},
    ],
)
def test_rest_invalid_parameters(data):
    image, _ = make_variant(1, "clean")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tampering/analyze",
            data=data,
            files={"document": ("demo.png", payload(image), "image/png")},
        )
    assert response.status_code == 422


def test_exif_orientation_overlay_geometry():
    exif = Image.Exif()
    exif[274] = 6
    stream = BytesIO()
    Image.new("RGB", (120, 60), (128, 128, 128)).save(stream, "JPEG", exif=exif)
    result = analyze_tampering(stream.getvalue(), include_cnn=False)
    assert (result.data.width, result.data.height) == (60, 120)


def test_actual_trained_checkpoint_when_installed():
    path = ROOT / "models" / "tamper_unet.pt"
    if not path.is_file():
        pytest.skip("Run synthetic training to install a checkpoint.")
    pytest.importorskip("torch")
    result, heat = predict(make_variant(8, "photo_replacement")[0])
    assert result.status == "ok" and heat.shape == (192, 192)
    assert np.isfinite(heat).all() and 0 <= heat.min() <= heat.max() <= 1
    assert result.metrics["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
