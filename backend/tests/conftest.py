"""Shared synthetic fixtures only."""

from datetime import date

import pytest
from app.demo import SyntheticIdentity, build_mrz
from app.layers.l1_ocr.mrz import parse_mrz
from app.schemas.common import FieldValue
from app.schemas.documents import ValidationRequest
from app.storage.database import seed_mock_database


@pytest.fixture
def db_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'mock.db').as_posix()}"
    seed_mock_database(url)
    return url


@pytest.fixture
def validation_request():
    identity = SyntheticIdentity()
    values = {
        "name": "EXAMPLE ALEX",
        "number": identity.number,
        "dob": identity.dob,
        "expiry": identity.expiry,
        "issue": identity.issue,
    }
    return ValidationRequest(
        document_type="passport",
        reference_date=date(2026, 10, 3),
        mrz=parse_mrz(build_mrz(identity)),
        viz_fields={
            name: FieldValue(raw=value, corrected=value, confidence=0.9, source="viz")
            for name, value in values.items()
        },
    )
