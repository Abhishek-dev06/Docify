"""Audit concurrency, append-only storage, replay behavior and corruption detection."""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.storage.audit import AuditConflict, AuditIntegrityError, AuditStore, digest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def store(tmp_path):
    result = AuditStore(f"sqlite:///{(tmp_path / 'audit.db').as_posix()}")
    yield result
    result.engine.dispose()


def record(store, key=None, doc="a" * 64):
    return store.record_scan(
        {
            "processing_status": "insufficient_evidence",
            "risk": {"score": 3.25, "missing_required_signals": ["liveness"]},
        },
        "DEMO-TEST",
        doc,
        key or str(uuid.uuid4()),
        digest({"document": doc}),
    )


def decision(
    store, scan, choice="secondary_inspection", key=None, ack=False, head=None
):
    return store.decide(
        scan["scan_id"],
        choice,
        "Reviewed synthetic evidence.",
        "DEMO-TEST",
        head or scan["event_hash"],
        key or str(uuid.uuid4()),
        ack,
    )


def test_empty_chain_and_anchor(store):
    assert store.verify()["event_count"] == 0
    assert store.verify((0, "0" * 64))["valid"]
    assert not store.verify((1, "1" * 64))["valid"]


def test_hashes_link_events_and_revisions_preserve_prior(store):
    scan = record(store)
    first = decision(store, scan)
    second = decision(store, scan, "reject", head=first["event_hash"])
    assert first["previous_hash"] == scan["event_hash"]
    assert second["previous_hash"] == first["event_hash"]
    assert len(store.get_scan(scan["scan_id"])["events"]) == 3
    assert (
        store.history()["items"][0]["latest_decision"]["payload"]["decision"]
        == "reject"
    )
    assert store.verify((2, first["event_hash"]))["valid"]


def test_scan_retry_and_key_collision(store):
    key = str(uuid.uuid4())
    a, b = record(store, key), record(store, key)
    assert a == b and store.verify()["event_count"] == 1
    with pytest.raises(AuditConflict):
        record(store, key, "b" * 64)


def test_decision_retry_is_exactly_once(store):
    scan, key = record(store), str(uuid.uuid4())
    a = decision(store, scan, key=key)
    assert decision(store, scan, key=key) == a
    assert store.verify()["event_count"] == 2
    with pytest.raises(AuditConflict):
        decision(store, scan, "reject", key=key)


def test_stale_decision_is_rejected(store):
    scan = record(store)
    decision(store, scan)
    with pytest.raises(AuditConflict, match="reload"):
        decision(store, scan, "reject")


def test_incomplete_approval_requires_acknowledgement(store):
    scan = record(store)
    with pytest.raises(AuditConflict, match="acknowledgement"):
        decision(store, scan, "approve")
    assert decision(store, scan, "approve", ack=True)["payload"][
        "acknowledge_incomplete"
    ]


def test_unknown_scan_cannot_be_decided(store):
    with pytest.raises(KeyError):
        decision(store, {"scan_id": str(uuid.uuid4()), "event_hash": "a" * 64})


@pytest.mark.parametrize(
    "sql", ["UPDATE audit_events SET actor='CHANGED'", "DELETE FROM audit_events"]
)
def test_database_blocks_edit_and_delete(store, sql):
    record(store)
    with pytest.raises(IntegrityError), store.engine.begin() as conn:
        conn.execute(text(sql))
    assert store.verify()["valid"]


def test_detects_payload_tampering_and_blocks_further_writes(store):
    record(store)
    with store.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_no_update"))
        conn.execute(
            text("UPDATE audit_events SET payload_json=:p"),
            {"p": json.dumps({"risk": 0})},
        )
    assert store.verify()["error"] == "EVENT_CHAIN_MISMATCH"
    with pytest.raises(AuditIntegrityError):
        record(store)
    with pytest.raises(AuditIntegrityError):
        store.history()


def test_detects_tail_deletion_against_stored_head_and_external_anchor(store):
    scan = record(store)
    with store.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_no_delete"))
        conn.execute(text("DELETE FROM audit_events"))
    assert store.verify()["error"] == "HEAD_MISMATCH"
    # A privileged attacker rewrites the mutable head as well.
    with store.engine.begin() as conn:
        conn.execute(text("UPDATE audit_head SET seq=0,event_hash=:h"), {"h": "0" * 64})
    assert store.verify()["valid"]  # Honest limit: no external anchor, no detection.
    assert store.verify((1, scan["event_hash"]))["error"] == "TRUSTED_ANCHOR_MISMATCH"


def test_parallel_writers_produce_one_contiguous_chain(store):
    with ThreadPoolExecutor(max_workers=6) as workers:
        rows = list(workers.map(lambda _: record(store), range(18)))
    assert sorted(r["seq"] for r in rows) == list(range(1, 19))
    assert store.verify()["valid"] and store.verify()["event_count"] == 18


def test_concurrent_same_scan_request_has_single_event(store):
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=4) as workers:
        rows = list(workers.map(lambda _: record(store, key), range(8)))
    assert len({r["event_id"] for r in rows}) == 1
    assert store.verify()["event_count"] == 1


def test_two_officers_cannot_silently_overwrite_same_review(store):
    scan = record(store)

    def attempt(_):
        try:
            return decision(store, scan)["event_id"]
        except AuditConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(attempt, range(2)))
    assert results.count("conflict") == 1
    assert store.verify()["event_count"] == 2


def test_history_filters_pagination_and_hash_search(store):
    first = record(store, doc="a" * 64)
    record(store, doc="b" * 64)
    decision(store, first)
    assert store.history("aaaa")["total"] == 1
    assert store.history(decision="pending")["total"] == 1
    assert store.history(decision="secondary_inspection")["total"] == 1
    assert len(store.history(limit=1, offset=1)["items"]) == 1
