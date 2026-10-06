"""HTTP contracts, in-memory uploads and failure handling."""

import tempfile
from datetime import date

import cv2
import numpy as np
import pytest
from app.demo import SyntheticIdentity, build_mrz
from app.main import app
from app.pipeline import analyze_phase1
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_and_documented_endpoints():
    assert client.get("/api/v1/health").json()["phase"] == 6
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/phase1/analyze"]["post"]
    assert "multipart/form-data" in operation["requestBody"]["content"]


def test_mrz_rest_contract():
    result = client.post(
        "/api/v1/ocr/parse-mrz", json={"lines": build_mrz(SyntheticIdentity())}
    )
    assert result.status_code == 200
    assert all(check["valid"] for check in result.json()["checks"])
    assert result.headers["cache-control"] == "no-store"


def test_validation_endpoint(validation_request, db_url, monkeypatch):
    monkeypatch.setenv("SCREENING_DATABASE_URL", db_url)
    response = client.post(
        "/api/v1/validation/check", json=validation_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    assert response.json()["data"]["mismatch_count"] == 0


def test_invalid_image_returns_structured_error():
    response = client.post(
        "/api/v1/capture/preprocess",
        files={"document": ("bad.png", b"bad", "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert response.json()["error"]["request_id"]


def test_missing_upload_is_clear():
    response = client.post(
        "/api/v1/capture/preprocess", files={"wrong": ("a.png", b"bad")}
    )
    assert response.status_code == 422


def test_upload_over_one_megabyte_never_spools_to_disk(monkeypatch):
    def forbidden_rollover(self):
        pytest.fail("An upload attempted to spool to disk.")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", forbidden_rollover)
    image = np.random.default_rng(7).integers(0, 256, (750, 1200, 3), dtype=np.uint8)
    payload = cv2.imencode(".png", image)[1].tobytes()
    assert len(payload) > 1024 * 1024
    response = client.post(
        "/api/v1/capture/preprocess", files={"document": ("synthetic.png", payload)}
    )
    assert response.status_code == 200


def test_large_body_is_rejected():
    response = client.post(
        "/api/v1/capture/preprocess",
        content=b"",
        headers={"Content-Length": str(11 * 1024 * 1024)},
    )
    assert response.status_code == 413


def test_bad_quality_short_circuits_ocr(monkeypatch):
    import app.pipeline as pipeline

    def forbidden_ocr(*args, **kwargs):
        pytest.fail("OCR should not run after a failed quality gate.")

    monkeypatch.setattr(pipeline, "extract_ocr", forbidden_ocr)
    image = np.zeros((800, 1200, 3), dtype=np.uint8)
    payload = cv2.imencode(".png", image)[1].tobytes()
    result = analyze_phase1(payload, date(2026, 10, 3))
    assert result.status == "needs_rescan"
    assert result.ocr is None and result.validation is None


def test_bad_document_type_and_reference_date():
    response = client.post(
        "/api/v1/capture/preprocess",
        data={"document_type": "alien"},
        files={"document": ("bad.png", b"x")},
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/phase1/analyze", files={"document": ("bad.png", b"x")}
    )
    assert response.status_code == 422
