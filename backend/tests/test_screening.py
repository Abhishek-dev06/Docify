"""Parallel execution, quality gating and partial-failure isolation."""

import base64
from datetime import date
from threading import Barrier

import cv2
import numpy as np
import pytest
from app import screening
from app.demo import SyntheticIdentity, build_mrz
from app.layers.l0_capture.preprocess import preprocess
from app.layers.l1_ocr.mrz import parse_mrz
from app.main import app
from app.schemas.common import LayerResult
from app.schemas.documents import OCRData
from app.schemas.faces import LivenessData, VerificationData
from fastapi.testclient import TestClient


@pytest.fixture
def fake_pipeline(monkeypatch):
    image = np.random.default_rng(1).integers(80, 180, (200, 300, 3), dtype=np.uint8)
    encoded = cv2.imencode(".png", image)[1].tobytes()
    capture = preprocess(image)
    capture.status = "ok"
    capture.data.image_base64 = base64.b64encode(encoded).decode()
    monkeypatch.setattr(screening, "preprocess", lambda *args: capture)
    monkeypatch.setattr(
        screening,
        "extract_ocr",
        lambda *args: LayerResult(
            data=OCRData(
                document_type="passport", mrz=parse_mrz(build_mrz(SyntheticIdentity()))
            )
        ),
    )
    monkeypatch.setattr(screening, "analyze_tampering", lambda *args: None)
    monkeypatch.setattr(
        screening,
        "verify_faces",
        lambda *args: LayerResult(
            data=VerificationData(
                threshold=0.6,
                cosine_similarity=0.9,
                match=True,
                decision="match",
                document_face_count=1,
                live_face_count=1,
            )
        ),
    )
    monkeypatch.setattr(
        screening, "evaluate_liveness", lambda *args: LayerResult(data=LivenessData())
    )
    return encoded, capture


def test_three_layers_run_concurrently(fake_pipeline, monkeypatch, db_url):
    payload, _ = fake_pipeline
    barrier = Barrier(3, timeout=5)
    validation = screening.validate_document
    face = screening.verify_faces

    def validate(*args):
        barrier.wait()
        return validation(*args)

    def tamper(*args):
        barrier.wait()
        return None

    def verify(*args):
        barrier.wait()
        return face(*args)

    monkeypatch.setattr(screening, "validate_document", validate)
    monkeypatch.setattr(screening, "analyze_tampering", tamper)
    monkeypatch.setattr(screening, "verify_faces", verify)
    result = screening.screen_document(
        payload, date(2026, 10, 3), live_payload=payload, db_url=db_url
    )
    assert not result.failures and result.face.data.match
    assert result.validation.data.database_available


def test_quality_failure_skips_all_later_layers(fake_pipeline, monkeypatch):
    payload, capture = fake_pipeline
    capture.status = "needs_rescan"
    monkeypatch.setattr(
        screening, "extract_ocr", lambda *a: pytest.fail("OCR must not run")
    )
    result = screening.screen_document(payload, date(2026, 10, 3))
    assert result.status == "needs_rescan" and result.risk.data.score is None
    assert result.ocr is result.validation is result.tampering is result.face is None


def test_layer_failure_does_not_erase_other_layers(fake_pipeline, monkeypatch, db_url):
    payload, _ = fake_pipeline

    def broken(*args):
        raise RuntimeError("Do not echo private payload in API error")

    monkeypatch.setattr(screening, "analyze_tampering", broken)
    result = screening.screen_document(
        payload, date(2026, 10, 3), live_payload=payload, db_url=db_url
    )
    assert result.validation and result.face and result.liveness
    assert result.failures[0].stage == "L3"
    assert "private payload" not in result.model_dump_json()
    assert (
        result.status == "insufficient_evidence" and result.risk.data.category is None
    )


def test_ocr_failure_still_runs_independent_evidence(fake_pipeline, monkeypatch):
    payload, _ = fake_pipeline

    def broken(*args):
        raise RuntimeError("OCR failed")

    monkeypatch.setattr(screening, "extract_ocr", broken)
    result = screening.screen_document(payload, date(2026, 10, 3), live_payload=payload)
    assert result.ocr is None and result.face and result.validation
    assert result.failures[0].stage == "L1"
    assert "mrz" in result.risk.data.missing_required_signals


def test_liveness_failure_retains_face_result(fake_pipeline, monkeypatch):
    payload, _ = fake_pipeline

    def broken(*args):
        raise RuntimeError("Liveness failed")

    monkeypatch.setattr(screening, "evaluate_liveness", broken)
    result = screening.screen_document(payload, date(2026, 10, 3), live_payload=payload)
    assert result.face and result.liveness is None
    assert result.failures[0].stage == "L4.liveness"


def test_portrait_mask_is_mapped_and_used_only_for_ocr(fake_pipeline, monkeypatch):
    payload, capture = fake_pipeline
    capture.data.transform = [[1, 0, -10], [0, 1, -5], [0, 0, 1]]
    received = {}
    original_ocr = screening.extract_ocr
    original_face = screening.verify_faces

    def ocr(image, kind):
        received["ocr"] = image.copy()
        return original_ocr(image, kind)

    def face(image, live):
        received["face"] = image.copy()
        return original_face(image, live)

    monkeypatch.setattr(screening, "extract_ocr", ocr)
    monkeypatch.setattr(screening, "verify_faces", face)
    result = screening.screen_document(
        payload,
        date(2026, 10, 3),
        live_payload=payload,
        photo_region=(0.5, 0.3, 0.2, 0.2),
    )
    assert np.all(received["ocr"][56:94, 141:199] == 255)
    assert np.all(received["face"][56:94, 141:199] < 255)
    assert np.array_equal(received["ocr"][:40], received["face"][:40])
    assert result.ocr.findings[-1].code == "PORTRAIT_EXCLUDED_FROM_OCR"
    assert result.risk.data.evidence_origin == "server_layers"


@pytest.mark.ocr
@pytest.mark.face_models
def test_real_blacklist_with_portrait_through_http(db_url, monkeypatch):
    from app.demo import generate_document
    from app.layers.l0_capture.preprocess import decode_image
    from app.layers.l1_ocr.engine import configure_tesseract
    from app.layers.l4_face.synthetic_identity_index import synthetic_portrait
    from app.settings import ROOT

    if (
        not configure_tesseract()
        or not (ROOT / "models" / "face_recognition_sface_2021dec.onnx").exists()
    ):
        pytest.skip("Install OCR and face models to run the real integration test.")
    monkeypatch.setenv("SCREENING_DATABASE_URL", db_url)
    document = decode_image(generate_document(SyntheticIdentity(number="Z9000001"))[0])
    portrait = synthetic_portrait("synthetic_a")
    document[245:555, 1200:1510] = cv2.resize(portrait, (310, 310))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/screening/analyze",
            files={
                "document": (
                    "demo.png",
                    cv2.imencode(".png", document)[1].tobytes(),
                    "image/png",
                ),
                "live": (
                    "live.png",
                    cv2.imencode(".png", portrait)[1].tobytes(),
                    "image/png",
                ),
            },
            data={
                "reference_date": "2026-10-03",
                "document_type": "passport",
                "photo_region": "[0.75,0.21,0.19375,0.46]",
            },
        )
    assert response.status_code == 200
    result = response.json()
    assert not result["failures"]
    assert result["validation"]["data"]["blacklist_hit"] is True
    assert result["risk"]["data"]["category"] == "High"
    assert result["face"]["data"]["match"] is True
    assert "liveness" in result["risk"]["data"]["missing_required_signals"]


@pytest.mark.parametrize(
    "timestamps",
    [
        None,
        [1, 1],
        [2, 1],
        [0, float("nan")],
        [0, None],
        [0, True],
        [0, 20001],
        [0],
        {},
    ],
)
def test_invalid_frame_timing_rejected_before_work(fake_pipeline, timestamps):
    payload, _ = fake_pipeline
    with pytest.raises(ValueError):
        screening.frame_inputs(None, [payload, payload], timestamps)


def test_live_and_sequence_mutually_exclusive(fake_pipeline):
    payload, _ = fake_pipeline
    with pytest.raises(ValueError):
        screening.frame_inputs(payload, [payload], [0])


def test_risk_api_and_policy():
    with TestClient(app) as client:
        policy = client.get("/api/v1/risk/policy").json()
        response = client.post("/api/v1/risk/score", json={"signals": {}})
        assert response.status_code == 200
        assert response.json()["data"]["policy_sha256"] == policy["sha256"]
        assert response.json()["data"]["category"] is None
        assert (
            client.post(
                "/api/v1/risk/score", json={"signals": {"unknown": {}}}
            ).status_code
            == 422
        )


def test_screening_http_contract(fake_pipeline):
    payload, _ = fake_pipeline
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/screening/analyze",
            files={"document": ("synthetic.png", payload, "image/png")},
            data={"reference_date": "2026-10-03"},
        )
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    assert response.json()["risk"]["data"]["category"] is None
    assert not response.json()["images_persisted"]


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"reference_date": "bad"},
        {"reference_date": "2026-10-03", "photo_region": "null"},
        {"reference_date": "2026-10-03", "timestamps_ms": "null"},
        {"reference_date": "2026-10-03", "timestamps_ms": "[0]"},
        {"reference_date": "2026-10-03", "unknown": "x"},
    ],
)
def test_bad_screening_fields(fake_pipeline, values):
    payload, _ = fake_pipeline
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/screening/analyze",
            files={"document": ("synthetic.png", payload, "image/png")},
            data=values,
        )
    assert response.status_code == 422
