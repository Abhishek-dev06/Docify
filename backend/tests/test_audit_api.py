"""Audited requests persist only allowlisted metadata and idempotent decisions."""

import uuid

import pytest
from app.api import audit
from app.main import app
from app.storage.audit import get_audit_store
from fastapi.testclient import TestClient
from test_screening import fake_pipeline  # noqa: F401


@pytest.fixture
def audit_env(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "AUDIT_DATABASE_URL", f"sqlite:///{(tmp_path / 'audit.db').as_posix()}"
    )
    return {"X-Officer-ID": "DEMO-QA", "Idempotency-Key": str(uuid.uuid4())}


def test_record_and_replay_without_reanalysis(fake_pipeline, audit_env, monkeypatch):  # noqa: F811
    image, _ = fake_pipeline
    with TestClient(app) as client:
        files = {"document": ("mock.png", image, "image/png")}
        data = {"reference_date": "2026-10-03"}
        response = client.post(
            "/api/v1/scans/analyze", files=files, data=data, headers=audit_env
        )
        assert response.status_code == 200
        event = response.json()["scan_event"]
        serialized = str(event["payload"])
        for forbidden in (
            "image_base64",
            "raw_text",
            "EXAMPLE ALEX",
            "Z9000000",
            "1988-04-12",
        ):
            assert forbidden not in serialized
        assert response.json()["analysis"] is not None
        monkeypatch.setattr(
            audit, "screen_document", lambda *a: pytest.fail("No repeat inference")
        )
        repeated = client.post(
            "/api/v1/scans/analyze", files=files, data=data, headers=audit_env
        )
        assert repeated.json()["replayed"] and repeated.json()["analysis"] is None
        assert repeated.json()["scan_event"] == event
        assert client.get("/api/v1/scans").json()["total"] == 1
        assert client.get("/api/v1/audit/verify").json()["valid"]
        body = {
            "decision": "secondary_inspection",
            "note": "Synthetic review completed.",
            "expected_event_hash": event["event_hash"],
            "request_id": str(uuid.uuid4()),
        }
        decision = client.post(
            f"/api/v1/scans/{event['scan_id']}/decisions", json=body, headers=audit_env
        )
        assert decision.status_code == 200
        assert (
            len(client.get(f"/api/v1/scans/{event['scan_id']}").json()["events"]) == 2
        )


def test_changed_upload_options_with_same_key_rejected(fake_pipeline, audit_env):  # noqa: F811
    image, _ = fake_pipeline
    with TestClient(app) as client:
        for day, expected in [("2026-10-03", 200), ("2026-10-04", 409)]:
            response = client.post(
                "/api/v1/scans/analyze",
                headers=audit_env,
                data={"reference_date": day},
                files={"document": ("mock.png", image, "image/png")},
            )
            assert response.status_code == expected


def test_actor_and_request_key_required(fake_pipeline, audit_env):  # noqa: F811
    image, _ = fake_pipeline
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/scans/analyze",
            data={"reference_date": "2026-10-03"},
            files={"document": ("mock.png", image, "image/png")},
        )
        assert response.status_code == 422


def test_invalid_decision_and_anchor_parameters(audit_env):
    with TestClient(app) as client:
        assert client.get("/api/v1/audit/verify?anchor_seq=1").status_code == 422
        assert client.get("/api/v1/scans?limit=101").status_code == 422
        assert client.get("/api/v1/scans?decision=invalid").status_code == 422
        response = client.post(
            f"/api/v1/scans/{uuid.uuid4()}/decisions",
            headers=audit_env,
            json={"decision": "approve", "note": "short"},
        )
        assert response.status_code == 422
    assert get_audit_store().verify()["event_count"] == 0
