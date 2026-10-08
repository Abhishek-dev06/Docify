"""L4 API schemas, invalid requests, privacy and actual synthetic inference."""

import tempfile

import cv2
import numpy as np
import pytest
from app.layers.l4_face.synthetic_identity_index import (
    check_synthetic_identity,
    synthetic_portrait,
)
from app.main import app
from app.schemas.faces import SyntheticIdentityRequest
from fastapi.testclient import TestClient
from test_faces import models_present

client = TestClient(app)


def png(image):
    return cv2.imencode(".png", image)[1].tobytes()


def test_l4_endpoints_are_documented():
    paths = client.get("/openapi.json").json()["paths"]
    assert {
        "/api/v1/faces/detect",
        "/api/v1/faces/verify",
        "/api/v1/faces/liveness",
        "/api/v1/demo/identities/check",
    } <= set(paths)


def test_missing_pair_and_extra_file_rejected():
    response = client.post(
        "/api/v1/faces/verify", files={"document": ("x.png", b"bad")}
    )
    assert response.status_code == 422
    files = [(name, ("x.png", b"bad")) for name in ["document", "live", "extra"]]
    assert client.post("/api/v1/faces/verify", files=files).status_code == 400


def test_liveness_timestamps_reject_wrong_types():
    response = client.post(
        "/api/v1/faces/liveness",
        data={"timestamps_ms": '["bad"]'},
        files={"frames": ("x.png", b"bad")},
    )
    assert response.status_code == 422


def test_synthetic_index_rejects_external_image_enrollment():
    result = client.post(
        "/api/v1/demo/identities/check",
        json={
            "sample_id": "external-person",
            "claimed_name": "SYNTHETIC ALPHA",
            "document_number": "DEMO-A001",
            "embedding": [1, 2, 3],
        },
    )
    assert result.status_code == 422
    result = client.post(
        "/api/v1/demo/identities/check",
        json={
            "sample_id": "synthetic_a",
            "claimed_name": "SYNTHETIC ALPHA",
            "document_number": "DEMO-A001",
            "embedding": [1, 2, 3],
        },
    )
    assert result.status_code == 422


def test_pair_uploads_never_spool_to_disk(monkeypatch, tmp_path):
    def forbid(self):
        pytest.fail("An image upload attempted disk rollover.")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", forbid)
    monkeypatch.setenv("FACE_MODEL_DIR", str(tmp_path))
    noisy = np.random.default_rng(21).integers(0, 256, (750, 1200, 3), dtype=np.uint8)
    payload = png(noisy)
    assert len(payload) > 1024 * 1024
    response = client.post(
        "/api/v1/faces/verify",
        files={
            "document": ("a.png", payload),
            "live": ("b.png", payload),
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["data"]["match"] is None
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.face_models
@pytest.mark.skipif(not models_present, reason="Face models not downloaded")
def test_real_verification_and_liveness_endpoints():
    payload = png(synthetic_portrait("synthetic_a"))
    response = client.post(
        "/api/v1/faces/verify",
        files={
            "document": ("a.png", payload),
            "live": ("a.png", payload),
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["match"] is True
    assert "embedding" not in response.text
    liveness = client.post(
        "/api/v1/faces/liveness", files={"frames": ("a.png", payload)}
    )
    assert liveness.status_code == 200
    assert liveness.json()["data"]["liveness_score"] is None


@pytest.mark.face_models
@pytest.mark.skipif(not models_present, reason="Face models not downloaded")
def test_real_faiss_synthetic_alias_rule():
    pytest.importorskip("faiss")
    same = check_synthetic_identity(
        SyntheticIdentityRequest(
            sample_id="synthetic_a",
            claimed_name="SYNTHETIC ALPHA",
            document_number="DEMO-A001",
        )
    )
    changed = check_synthetic_identity(
        SyntheticIdentityRequest(
            sample_id="synthetic_a",
            claimed_name="SYNTHETIC ALIAS",
            document_number="DEMO-A002",
        )
    )
    assert same.status == changed.status == "ok"
    assert same.data.duplicate_identity_hit is False
    assert changed.data.duplicate_identity_hit is True
    assert len(changed.data.reasons) == 2
    assert not changed.data.embeddings_persisted
