"""Transactional append-only audit chain, with explicit integrity verification."""

import hashlib
import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Integer, String, Text, create_engine, select, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.settings import audit_database_url

ZERO_HASH = "0" * 64


class AuditConflict(ValueError):
    pass


class AuditIntegrityError(ValueError):
    pass


class AuditBase(DeclarativeBase):
    pass


class AuditEvent(AuditBase):
    __tablename__ = "audit_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    scan_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    timestamp: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(64))
    document_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    previous_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)


class AuditHead(AuditBase):
    __tablename__ = "audit_head"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_hash: Mapped[str] = mapped_column(String(64))


def canonical(value: dict) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def row_hash(row: dict) -> str:
    return digest({k: v for k, v in row.items() if k != "event_hash"})


def public_event(row: dict) -> dict:
    return {
        k: v for k, v in row.items() if k not in {"payload_json", "fingerprint"}
    } | {"payload": json.loads(row["payload_json"])}


class AuditStore:
    def __init__(self, url: str):
        parsed = make_url(url)
        self.sqlite = parsed.get_backend_name() == "sqlite"
        if self.sqlite and parsed.database not in {None, ":memory:"}:
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url,
            connect_args={"timeout": 30, "check_same_thread": False}
            if self.sqlite
            else {},
        )
        AuditBase.metadata.create_all(self.engine)
        with self.transaction(write=True) as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_head (id,seq,event_hash) VALUES (1,0,:h) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"h": ZERO_HASH},
            )
            if self.sqlite:
                for action in ("UPDATE", "DELETE"):
                    conn.execute(
                        text(
                            f"CREATE TRIGGER IF NOT EXISTS audit_no_{action.lower()} "
                            f"BEFORE {action} ON audit_events BEGIN "
                            "SELECT RAISE(ABORT, 'audit events are append-only'); END"
                        )
                    )

    @contextmanager
    def transaction(self, write=False):
        with self.engine.connect() as conn:
            if self.sqlite:
                conn.exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")
            else:
                conn.begin()
                conn.execute(
                    select(AuditHead.__table__)
                    .where(AuditHead.id == 1)
                    .with_for_update(read=not write)
                )
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _rows(self, conn: Connection) -> list[dict]:
        return [
            dict(r)
            for r in conn.execute(
                select(AuditEvent.__table__).order_by(AuditEvent.seq)
            ).mappings()
        ]

    def _verify(
        self, conn: Connection, rows: list[dict], anchor: tuple | None = None
    ) -> dict:
        previous = ZERO_HASH
        for index, row in enumerate(rows, 1):
            if (
                row["seq"] != index
                or row["previous_hash"] != previous
                or row_hash(row) != row["event_hash"]
            ):
                return {
                    "valid": False,
                    "error": "EVENT_CHAIN_MISMATCH",
                    "failed_seq": index,
                }
            try:
                json.loads(row["payload_json"])
            except (ValueError, TypeError):
                return {"valid": False, "error": "INVALID_PAYLOAD", "failed_seq": index}
            previous = row["event_hash"]
        head = (
            conn.execute(select(AuditHead.__table__).where(AuditHead.id == 1))
            .mappings()
            .first()
        )
        if not head or head["seq"] != len(rows) or head["event_hash"] != previous:
            return {
                "valid": False,
                "error": "HEAD_MISMATCH",
                "failed_seq": len(rows) + 1,
            }
        if anchor:
            seq, expected = anchor
            actual = (
                ZERO_HASH
                if seq == 0
                else rows[seq - 1]["event_hash"]
                if seq <= len(rows)
                else None
            )
            if actual != expected:
                return {
                    "valid": False,
                    "error": "TRUSTED_ANCHOR_MISMATCH",
                    "failed_seq": seq,
                }
        return {
            "valid": True,
            "event_count": len(rows),
            "head_seq": len(rows),
            "head_hash": previous,
            "anchor_checked": anchor is not None,
            "limitation": "A database owner can rewrite the chain; "
            "retain an external trusted checkpoint.",
        }

    def verify(self, anchor: tuple | None = None) -> dict:
        with self.transaction() as conn:
            return self._verify(conn, self._rows(conn), anchor)

    def _checked(self, conn):
        rows = self._rows(conn)
        result = self._verify(conn, rows)
        if not result["valid"]:
            raise AuditIntegrityError(
                "Audit integrity verification failed; writes and history are blocked."
            )
        return rows

    def _append(
        self,
        conn,
        rows,
        *,
        scan_id,
        kind,
        actor,
        document_hash,
        payload,
        request_id,
        fingerprint,
    ):
        row = {
            "seq": len(rows) + 1,
            "event_id": str(uuid.uuid4()),
            "request_id": request_id,
            "fingerprint": fingerprint,
            "scan_id": scan_id,
            "kind": kind,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "actor": actor,
            "document_hash": document_hash,
            "payload_json": canonical(payload),
            "previous_hash": rows[-1]["event_hash"] if rows else ZERO_HASH,
        }
        row["event_hash"] = row_hash(row)
        conn.execute(AuditEvent.__table__.insert().values(**row))
        conn.execute(
            AuditHead.__table__.update()
            .where(AuditHead.id == 1)
            .values(seq=row["seq"], event_hash=row["event_hash"])
        )
        return public_event(row)

    @staticmethod
    def _retry(rows, request_id, fingerprint):
        for row in rows:
            if row["request_id"] == request_id:
                if row["fingerprint"] != fingerprint:
                    raise AuditConflict(
                        "Idempotency key was already used for a different request."
                    )
                return public_event(row)
        return None

    def record_scan(
        self,
        payload: dict,
        actor: str,
        document_hash: str,
        request_id: str,
        fingerprint: str,
    ) -> dict:
        with self.transaction(write=True) as conn:
            rows = self._checked(conn)
            retry = self._retry(rows, request_id, fingerprint)
            if retry:
                return retry
            return self._append(
                conn,
                rows,
                scan_id=str(uuid.uuid4()),
                kind="scan",
                actor=actor,
                document_hash=document_hash,
                payload=payload,
                request_id=request_id,
                fingerprint=fingerprint,
            )

    def decide(
        self,
        scan_id: str,
        decision: str,
        note: str,
        actor: str,
        expected_event_hash: str,
        request_id: str,
        acknowledge_incomplete: bool,
    ) -> dict:
        fingerprint = digest(
            {
                "scan_id": scan_id,
                "decision": decision,
                "note": note,
                "actor": actor,
                "expected_event_hash": expected_event_hash,
                "acknowledge_incomplete": acknowledge_incomplete,
            }
        )
        with self.transaction(write=True) as conn:
            rows = self._checked(conn)
            retry = self._retry(rows, request_id, fingerprint)
            if retry:
                return retry
            events = [r for r in rows if r["scan_id"] == scan_id]
            if not events or events[0]["kind"] != "scan":
                raise KeyError("Scan not found.")
            if events[-1]["event_hash"] != expected_event_hash:
                raise AuditConflict(
                    "Another decision was recorded; reload the scan before deciding."
                )
            scan = json.loads(events[0]["payload_json"])
            if (
                decision == "approve"
                and (
                    scan["risk"]["missing_required_signals"]
                    or scan["processing_status"] != "ok"
                )
                and not acknowledge_incomplete
            ):
                raise AuditConflict(
                    "Approval requires explicit acknowledgement of incomplete evidence."
                )
            return self._append(
                conn,
                rows,
                scan_id=scan_id,
                kind="decision",
                actor=actor,
                document_hash=events[0]["document_hash"],
                request_id=request_id,
                fingerprint=fingerprint,
                payload={
                    "decision": decision,
                    "note": note,
                    "acknowledge_incomplete": acknowledge_incomplete,
                    "supersedes_event_hash": events[-1]["event_hash"],
                    "actor_verified": False,
                },
            )

    def history(self, query="", decision=None, limit=20, offset=0) -> dict:
        with self.transaction() as conn:
            rows = self._checked(conn)
        scans = {}
        for row in rows:
            event = public_event(row)
            if row["kind"] == "scan":
                scans[row["scan_id"]] = {
                    "scan": event,
                    "latest_decision": None,
                    "latest_event_hash": row["event_hash"],
                }
            elif row["kind"] == "decision" and row["scan_id"] in scans:
                scans[row["scan_id"]]["latest_decision"] = event
                scans[row["scan_id"]]["latest_event_hash"] = row["event_hash"]
        result = []
        for value in reversed(list(scans.values())):
            event, latest = value["scan"], value["latest_decision"]
            state = latest["payload"]["decision"] if latest else "pending"
            haystack = " ".join(
                [
                    event["scan_id"],
                    event["document_hash"],
                    event["actor"],
                    latest["actor"] if latest else "",
                ]
            ).lower()
            if query.lower() in haystack and (decision is None or decision == state):
                result.append(value)
        return {
            "items": result[offset : offset + limit],
            "total": len(result),
            "limit": limit,
            "offset": offset,
        }

    def get_scan(self, scan_id: str) -> dict:
        with self.transaction() as conn:
            rows = [r for r in self._checked(conn) if r["scan_id"] == scan_id]
        if not rows:
            raise KeyError("Scan not found.")
        return {
            "events": [public_event(r) for r in rows],
            "latest_event_hash": rows[-1]["event_hash"],
        }


_store_lock = threading.Lock()
_store_registry: set[AuditStore] = set()


@lru_cache(maxsize=4)
def _store(url: str) -> AuditStore:
    store = AuditStore(url)
    _store_registry.add(store)
    return store


def get_audit_store() -> AuditStore:
    url = audit_database_url()
    with _store_lock:
        return _store(url)


def dispose_audit_stores() -> None:
    """Release SQLite handles on worker shutdown and during isolated tests."""
    with _store_lock:
        for store in _store_registry:
            store.engine.dispose()
        _store_registry.clear()
        _store.cache_clear()
