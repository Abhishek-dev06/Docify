"""Rule outcomes, uncertainty and read-only mock lookups."""

from datetime import date

from app.demo import SyntheticIdentity, build_mrz
from app.layers.l1_ocr.mrz import parse_mrz
from app.layers.l2_validation.checks import validate_document
from app.schemas.common import FieldValue
from app.schemas.documents import ValidationRequest
from app.storage.database import lookup_document, seed_mock_database


def codes(result):
    return {finding.code for finding in result.findings}


def test_consistent_document(validation_request, db_url):
    result = validate_document(validation_request, db_url)
    assert result.status == "ok"
    assert result.data.mismatch_count == 0
    assert result.data.blacklist_hit is False
    assert result.data.resolved_dates["dob"] == "1988-04-12"
    assert not any(f.severity in {"medium", "high"} for f in result.findings)


def test_altered_dob(validation_request, db_url):
    validation_request.viz_fields["dob"].corrected = "1998-04-12"
    result = validate_document(validation_request, db_url)
    assert result.data.mismatch_count == 1
    assert "FIELD_MISMATCH" in codes(result)


def test_recomputes_untrusted_supplied_checks(validation_request, db_url):
    lines = validation_request.mrz.raw_lines
    lines[1] = lines[1][:-1] + str((int(lines[1][-1]) + 1) % 10)
    assert all(check.valid for check in validation_request.mrz.checks)
    result = validate_document(validation_request, db_url)
    assert "MRZ_CHECK_FAILED" in codes(result)
    assert result.status == "ok"  # Processing succeeded; this is not an approval.


def test_expired_document_and_issue_order(validation_request, db_url):
    validation_request.mrz = parse_mrz(
        build_mrz(SyntheticIdentity(expiry="2020-10-03"))
    )
    validation_request.viz_fields["expiry"].corrected = "2020-10-03"
    result = validate_document(validation_request, db_url)
    assert {"DOCUMENT_EXPIRED", "ISSUE_EXPIRY_ORDER"} <= codes(result)


def test_invalid_calendar_date(validation_request, db_url):
    lines = validation_request.mrz.raw_lines
    lines[1] = lines[1][:13] + "881332" + lines[1][19:]
    assert "INVALID_MRZ_DATE" in codes(validate_document(validation_request, db_url))


def test_future_printed_birth(validation_request, db_url):
    validation_request.viz_fields["dob"].corrected = "2030-04-12"
    assert "DOB_IMPLAUSIBLE" in codes(validate_document(validation_request, db_url))


def test_century_ambiguity_is_not_silently_resolved(validation_request, db_url):
    validation_request.mrz = parse_mrz(build_mrz(SyntheticIdentity(dob="2010-04-12")))
    validation_request.viz_fields.pop("dob")
    result = validate_document(validation_request, db_url)
    assert "DOB_CENTURY_AMBIGUOUS" in codes(result)
    assert result.data.resolved_dates["dob"] is None


def test_absent_viz_does_not_become_match(validation_request, db_url):
    validation_request.viz_fields.clear()
    result = validate_document(validation_request, db_url)
    assert all(check.consistent is None for check in result.data.cross_checks)
    assert "CROSS_CHECK_INCOMPLETE" in codes(result)


def test_blacklist_and_history_are_mock_and_read_only(validation_request, db_url):
    seed_mock_database(db_url)
    validation_request.mrz = parse_mrz(build_mrz(SyntheticIdentity(number="Z9000001")))
    first = validate_document(validation_request, db_url)
    second = validate_document(validation_request, db_url)
    assert first.data.blacklist_hit is True
    assert first.data.previously_seen == second.data.previously_seen == 2
    assert lookup_document("UTO", "Z9000002", db_url)["previously_seen"] == 3


def test_lookup_unavailable_does_not_become_clear(validation_request, tmp_path):
    db_file = tmp_path / "absent.db"
    result = validate_document(validation_request, f"sqlite:///{db_file.as_posix()}")
    assert result.data.blacklist_hit is None
    assert not db_file.exists()


def test_country_code_and_number_policy(validation_request, db_url):
    validation_request.mrz = parse_mrz(build_mrz(SyntheticIdentity(country="ZZZ")))
    assert "COUNTRY_CODE_UNKNOWN" in codes(
        validate_document(validation_request, db_url)
    )
    validation_request.mrz = parse_mrz(build_mrz(SyntheticIdentity(number="12345")))
    assert "COUNTRY_NUMBER_FORMAT" in codes(
        validate_document(validation_request, db_url)
    )


def test_visa_stay_window_is_policy_review_not_rejection(db_url):
    values = {
        "valid_from": "2026-10-01",
        "valid_until": "2026-10-10",
        "stay_duration": "30 DAYS",
    }
    request = ValidationRequest(
        document_type="visa",
        reference_date=date(2026, 10, 3),
        viz_fields={
            k: FieldValue(raw=v, corrected=v, source="viz") for k, v in values.items()
        },
    )
    result = validate_document(request, db_url)
    assert "VISA_STAY_POLICY_REVIEW" in codes(result)
    assert (
        next(f for f in result.findings if f.code == "VISA_STAY_POLICY_REVIEW").severity
        == "info"
    )
