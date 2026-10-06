"""Checks report evidence and uncertainty; they never approve/reject a person."""

import re
import time
from datetime import date, datetime

import pycountry

from app.layers.l1_ocr.mrz import parse_mrz
from app.schemas.common import FieldValue, Finding, LayerResult
from app.schemas.documents import CrossCheck, ValidationData, ValidationRequest
from app.settings import load_config
from app.storage.database import lookup_document


def parse_printed_date(value: str | None) -> date | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None


def mrz_date_candidates(value: str | None, reference: date) -> list[date]:
    if not value or not re.fullmatch(r"\d{6}", value):
        return []
    century = reference.year // 100 * 100
    result = []
    for base in (century - 100, century, century + 100):
        try:
            result.append(date(base + int(value[:2]), int(value[2:4]), int(value[4:])))
        except ValueError:
            continue
    return result


def _value(fields: dict[str, FieldValue], name: str) -> str | None:
    field = fields.get(name)
    return field.corrected if field else None


def _normalized(value: str, name: str) -> str:
    normalized = " ".join(re.sub(r"[^A-Z0-9 ]", " ", value.upper()).split())
    return (
        " ".join(sorted(normalized.split()))
        if name == "name"
        else normalized.replace(" ", "")
    )


def validate_document(
    request: ValidationRequest, db_url: str | None = None
) -> LayerResult[ValidationData]:
    started = time.perf_counter()
    cfg = load_config("validation_rules.yaml")
    findings: list[Finding] = []
    reference = request.reference_date

    def flag(
        code: str, message: str, field: str | None = None, severity: str = "medium"
    ) -> None:
        findings.append(
            Finding(code=code, explanation=message, field=field, severity=severity)
        )

    # Recompute from raw lines: callers cannot supply fabricated valid check results.
    mrz = parse_mrz(request.mrz.raw_lines) if request.mrz else None
    fields = mrz.fields if mrz else {}
    checks = mrz.checks if mrz else []
    if mrz is None:
        flag("MRZ_UNAVAILABLE", "MRZ checks are unavailable.", severity="info")
    else:
        for check in checks:
            if check.valid is False:
                flag(
                    "MRZ_CHECK_FAILED",
                    f"{check.field}: observed {check.observed}, "
                    f"expected {check.expected}. Review signal only.",
                    check.field,
                )
        for limitation in mrz.limitations:
            flag("MRZ_VARIANT_UNSUPPORTED", limitation, severity="info")
        if mrz.corrections:
            flag(
                "MRZ_OCR_CORRECTED",
                "Check digits use position-corrected OCR. "
                "Inspect the preserved raw text.",
                severity="low",
            )
    viz = request.viz_fields
    cross_checks: list[CrossCheck] = []
    resolved: dict[str, str | None] = {}
    dates: dict[str, date | None] = {}
    for name in ("dob", "expiry"):
        mrz_value = _value(fields, name)
        viz_value = _value(viz, name)
        printed = parse_printed_date(viz_value)
        if viz_value and printed is None:
            flag("DATE_UNREADABLE", f"Cannot parse printed {name}: {viz_value}.", name)
        candidates = mrz_date_candidates(mrz_value, reference)
        if mrz_value and not candidates:
            flag(
                "INVALID_MRZ_DATE",
                f"MRZ {name} is not a complete valid calendar date.",
                name,
            )
        if name == "dob":
            candidates = [
                d
                for d in candidates
                if d <= reference
                and (
                    reference.year
                    - d.year
                    - ((reference.month, reference.day) < (d.month, d.day))
                )
                <= cfg["max_age"]
            ]
        else:
            candidates.sort(key=lambda d: abs((d - reference).days))
        resolved_date = None
        if printed and printed in candidates:
            resolved_date = printed
        elif name == "dob" and len(candidates) == 1:
            resolved_date = candidates[0]
        elif name == "expiry" and candidates:
            resolved_date = candidates[0]
            flag(
                "EXPIRY_CENTURY_INFERRED",
                "Expiry century selected nearest the reference "
                "date; verify against the printed four-digit year.",
                name,
                "info",
            )
        elif name == "dob" and len(candidates) > 1:
            flag(
                "DOB_CENTURY_AMBIGUOUS",
                "Two-digit MRZ year has multiple plausible "
                "centuries; a readable printed DOB is required.",
                name,
                "info",
            )
        dates[name] = resolved_date or printed
        resolved[name] = dates[name].isoformat() if dates[name] else None
        # Different calendar centuries cannot be inferred solely from YYMMDD.
        consistent = None
        if mrz_value and printed and candidates:
            consistent = printed in candidates
            if not consistent:
                flag("FIELD_MISMATCH", f"MRZ and printed {name} disagree.", name)
        cross_checks.append(
            CrossCheck(
                field=name,
                mrz_value=mrz_value,
                viz_value=viz_value,
                consistent=consistent,
            )
        )
        # Check every available source: a later VIZ expiry must not mask an expired MRZ.
        source_dates = {d for d in (resolved_date, printed) if d}
        for value in source_dates:
            if name == "expiry" and value < reference:
                flag(
                    "DOCUMENT_EXPIRED",
                    f"An observed expiry is {value}; reference is {reference}.",
                    name,
                )
            if (
                name == "expiry"
                and value.year > reference.year + cfg["max_expiry_horizon_years"]
            ):
                flag(
                    "EXPIRY_IMPLAUSIBLE",
                    "Expiry exceeds the configured future horizon.",
                    name,
                )
            if name == "dob":
                age = (
                    reference.year
                    - value.year
                    - ((reference.month, reference.day) < (value.month, value.day))
                )
                if value > reference or age > cfg["max_age"]:
                    flag(
                        "DOB_IMPLAUSIBLE",
                        "DOB is in the future or exceeds the configured age limit.",
                        name,
                    )
    for name in ("name", "number"):
        left, right = _value(fields, name), _value(viz, name)
        consistent = (
            _normalized(left, name) == _normalized(right, name)
            if left and right
            else None
        )
        cross_checks.append(
            CrossCheck(
                field=name, mrz_value=left, viz_value=right, consistent=consistent
            )
        )
        if consistent is False:
            flag("FIELD_MISMATCH", f"MRZ and printed {name} disagree.", name)
    if any(check.consistent is None for check in cross_checks):
        flag(
            "CROSS_CHECK_INCOMPLETE",
            "Some MRZ/VIZ comparisons lack readable evidence.",
            severity="info",
        )
    issue_text = _value(viz, "issue")
    issue = parse_printed_date(issue_text)
    if issue_text and issue is None:
        flag("DATE_UNREADABLE", "Issue date could not be parsed.", "issue")
    if issue and dates.get("expiry") and issue >= dates["expiry"]:
        flag("ISSUE_EXPIRY_ORDER", "Issue date must precede expiry.", "issue")
    if issue and issue > reference:
        flag("FUTURE_ISSUE", "Issue date is later than the reference date.", "issue")
    if issue and dates.get("dob") and issue < dates["dob"]:
        flag("ISSUE_BEFORE_BIRTH", "Issue date precedes DOB.", "issue")
    valid_from = parse_printed_date(_value(viz, "valid_from"))
    valid_until = parse_printed_date(_value(viz, "valid_until"))
    for key, parsed in [("valid_from", valid_from), ("valid_until", valid_until)]:
        if _value(viz, key) and parsed is None:
            flag("DATE_UNREADABLE", f"Cannot parse {key}.", key)
    if valid_from and valid_until and valid_from > valid_until:
        flag("VISA_WINDOW_INVALID", "Visa validity starts after it ends.")
    if valid_from and reference < valid_from:
        flag("VISA_NOT_YET_VALID", "Reference date is before the visa entry window.")
    if valid_until and reference > valid_until:
        flag(
            "VISA_ENTRY_WINDOW_EXPIRED",
            "Reference date is after the visa entry window.",
        )
    stay = _value(viz, "stay_duration")
    if stay:
        match = re.fullmatch(r"(\d+)\s*(?:DAYS?)?", stay.strip(), re.I)
        if not match or int(match[1]) <= 0:
            flag(
                "VISA_STAY_INVALID", "Stay duration must be a positive number of days."
            )
        elif (
            valid_from
            and valid_until
            and int(match[1]) > (valid_until - valid_from).days + 1
        ):
            flag(
                "VISA_STAY_POLICY_REVIEW",
                "Stay duration exceeds the entry-window length. "
                "This may be legitimate; country-specific visa policy is needed.",
                severity="info",
            )
    valid_codes = {country.alpha_3 for country in pycountry.countries} | set(
        cfg["extra_country_codes"]
    )
    for name in ("issuing_country", "nationality"):
        value = _value(fields, name)
        if value and value not in valid_codes:
            flag(
                "COUNTRY_CODE_UNKNOWN", f"Unrecognized MRZ country code: {value}.", name
            )
    country = _value(fields, "issuing_country")
    number = _value(fields, "number") or _value(viz, "number")
    if number:
        if not re.fullmatch(r"[A-Z0-9]{5,20}", number):
            flag(
                "NUMBER_FORMAT",
                "Document number violates the generic demo format policy.",
                "number",
            )
        pattern = cfg["passport_number_patterns"].get(country)
        if (
            request.document_type == "passport"
            and pattern
            and not re.fullmatch(pattern, number)
        ):
            flag(
                "COUNTRY_NUMBER_FORMAT",
                "Number violates the configured synthetic-country policy.",
                "number",
            )
    database = {"available": False, "blacklist_hit": None, "previously_seen": None}
    if country and number:
        database = lookup_document(country, number, db_url)
    if not database["available"]:
        flag(
            "LOOKUP_UNAVAILABLE",
            "Mock lookup is unavailable or lacks an issuer/number.",
            severity="info",
        )
    if database["blacklist_hit"]:
        flag(
            "MOCK_BLACKLIST_HIT",
            "Document matches a fictional blacklist entry.",
            severity="high",
        )
    if database["previously_seen"]:
        flag(
            "PREVIOUSLY_SEEN",
            f"Mock database contains {database['previously_seen']} previous sightings. "
            "Repeat travel alone does not imply fraud.",
            severity="info",
        )
    enough = mrz is not None and not mrz.limitations
    return LayerResult(
        status="ok" if enough else "insufficient_evidence",
        data=ValidationData(
            checks=checks,
            cross_checks=cross_checks,
            mismatch_count=sum(c.consistent is False for c in cross_checks),
            resolved_dates=resolved,
            blacklist_hit=database["blacklist_hit"],
            previously_seen=database["previously_seen"],
            database_available=database["available"],
        ),
        findings=findings,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
