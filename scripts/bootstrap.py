"""Initialize only synthetic lookup fixtures and an empty audit schema."""

from app.storage.audit import get_audit_store
from app.storage.database import seed_mock_database

if __name__ == "__main__":
    seed_mock_database()
    status = get_audit_store().verify()
    if not status["valid"]:
        raise SystemExit("Audit integrity check failed; startup blocked.")
    print(f"Synthetic lookup ready; audit verified ({status['event_count']} events).")
