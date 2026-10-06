"""SQLAlchemy lookup store. Validation reads never create or modify records."""

import hashlib
from pathlib import Path

from sqlalchemy import String, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.settings import database_url


class Base(DeclarativeBase):
    pass


class MockDocument(Base):
    __tablename__ = "mock_documents"
    document_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    blacklisted: Mapped[bool] = mapped_column(default=False)
    seen_count: Mapped[int] = mapped_column(default=0)


def document_key(country: str, number: str) -> str:
    value = f"{country.upper().strip()}:{number.upper().strip()}"
    return hashlib.sha256(value.encode()).hexdigest()


def lookup_document(country: str, number: str, url: str | None = None) -> dict:
    url = url or database_url()
    engine = None
    try:
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite" and parsed.database != ":memory:":
            if not parsed.database or not Path(parsed.database).is_file():
                return {
                    "available": False,
                    "blacklist_hit": None,
                    "previously_seen": None,
                }
        engine = create_engine(url)
        with Session(engine) as session:
            record = session.get(MockDocument, document_key(country, number))
            return {
                "available": True,
                "blacklist_hit": record.blacklisted if record else False,
                "previously_seen": record.seen_count if record else 0,
            }
    except (SQLAlchemyError, ImportError):
        return {"available": False, "blacklist_hit": None, "previously_seen": None}
    finally:
        if engine is not None:
            engine.dispose()


def seed_mock_database(url: str | None = None) -> None:
    """Idempotently seed fictional records only. Never ingest personal data."""
    url = url or database_url()
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session, session.begin():
            for number, blocked, seen in [
                ("Z9000001", True, 2),
                ("Z9000002", False, 3),
            ]:
                key = document_key("UTO", number)
                if session.get(MockDocument, key) is None:
                    session.add(
                        MockDocument(
                            document_key=key, blacklisted=blocked, seen_count=seen
                        )
                    )
    finally:
        engine.dispose()
