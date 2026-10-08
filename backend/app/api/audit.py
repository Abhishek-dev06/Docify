"""Opt-in audited scans, decision events and privacy-minimized searchable history."""

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.risk import screening_arguments
from app.schemas.audit import DecisionRequest, Officer
from app.screening import ScreeningResult, screen_document
from app.storage.audit import (
    AuditConflict,
    AuditIntegrityError,
    digest,
    get_audit_store,
)

router = APIRouter(prefix="/api/v1", tags=["L6 audit"])


def actor_name(value: str) -> str:
    try:
        return Officer(name=value).name
    except ValidationError as exc:
        raise HTTPException(
            422, "Officer label must be 3..64 letters, digits, _ or -."
        ) from exc


def audit_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (AuditConflict, AuditIntegrityError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "Scan not found.") from exc
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(
            503, "Audit storage unavailable; no successful write confirmed."
        ) from exc


def summary(result: ScreeningResult) -> dict:
    """Allowlist only review metadata; never persist extracted identities or images."""
    validation = result.validation.data if result.validation else None
    return {
        "reference_date": result.reference_date.isoformat(),
        "processing_status": result.status,
        "document_type": result.ocr.data.document_type
        if result.ocr
        else result.capture.data.document_type,
        "risk": result.risk.data.model_dump(mode="json"),
        "layer_statuses": {
            n: getattr(result, n).status if getattr(result, n) else "not_run"
            for n in ("capture", "ocr", "validation", "tampering", "face", "liveness")
        },
        "mismatch_fields": [
            c.field for c in validation.cross_checks if c.consistent is False
        ]
        if validation
        else [],
        "failed_check_fields": [c.field for c in validation.checks if c.valid is False]
        if validation
        else [],
        "face_similarity": result.face.data.cosine_similarity if result.face else None,
        "face_decision": result.face.data.decision if result.face else "undetermined",
        "duration_ms": result.duration_ms,
        "failure_stages": [f.stage for f in result.failures],
        "actor_verified": False,
        "images_retained": False,
    }


def fingerprint(args: tuple, actor: str) -> str:
    doc, reference, kind, live, region, frames, timestamps = args

    def sha(value):
        return hashlib.sha256(value).hexdigest() if value is not None else None

    return digest(
        {
            "document": sha(doc),
            "reference_date": reference.isoformat(),
            "document_type": kind,
            "live": sha(live),
            "photo_region": region,
            "frames": [sha(b) for b in frames] if frames else None,
            "timestamps_ms": timestamps,
            "actor": actor,
        }
    )


@router.post("/scans/analyze")
async def analyze_and_record(
    request: Request,
    x_officer_id: Annotated[str, Header()],
    idempotency_key: Annotated[UUID, Header()],
) -> dict:
    actor = actor_name(x_officer_id)
    args = await screening_arguments(request)

    def run():
        store = get_audit_store()
        key, fp = str(idempotency_key), fingerprint(args, actor)
        with store.transaction() as conn:
            prior = store._retry(store._checked(conn), key, fp)
        if prior:
            return {"analysis": None, "scan_event": prior, "replayed": True}
        result = screen_document(*args)
        payload = summary(result)
        event = store.record_scan(payload, actor, result.document_hash, key, fp)
        same_result = event["payload"] == payload
        return {
            "analysis": result.model_dump(mode="json") if same_result else None,
            "scan_event": event,
            "replayed": not same_result,
        }

    return await run_in_threadpool(lambda: audit_call(run))


@router.get("/scans")
def history(
    q: str = Query(default="", max_length=128),
    decision: Literal["approve", "secondary_inspection", "reject", "pending"]
    | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return audit_call(lambda: get_audit_store().history(q, decision, limit, offset))


@router.get("/scans/{scan_id}")
def detail(scan_id: UUID) -> dict:
    return audit_call(lambda: get_audit_store().get_scan(str(scan_id)))


@router.post("/scans/{scan_id}/decisions")
def decide(
    scan_id: UUID, request: DecisionRequest, x_officer_id: Annotated[str, Header()]
) -> dict:
    actor = actor_name(x_officer_id)
    return audit_call(
        lambda: get_audit_store().decide(
            str(scan_id),
            request.decision,
            request.note,
            actor,
            request.expected_event_hash,
            str(request.request_id),
            request.acknowledge_incomplete,
        )
    )


@router.get("/audit/verify")
def verify(
    anchor_seq: int | None = Query(default=None, ge=0),
    anchor_hash: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"),
) -> dict:
    if (anchor_seq is None) != (anchor_hash is None):
        raise HTTPException(422, "Supply both anchor_seq and anchor_hash.")
    return audit_call(
        lambda: get_audit_store().verify(
            (anchor_seq, anchor_hash) if anchor_seq is not None else None
        )
    )
