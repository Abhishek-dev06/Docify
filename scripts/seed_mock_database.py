"""Seed fictional blacklist and prior-sighting records."""

from app.storage.database import seed_mock_database

if __name__ == "__main__":
    seed_mock_database()
    print("Seeded UTO/Z9000001 (blacklisted) and UTO/Z9000002 (previously seen).")
