"""Conservative English label extraction; never synthesize VIZ from MRZ."""

import re

from app.schemas.common import DocumentType, FieldValue

LABELS = {
    "name": r"(?:FULL\s+NAME|NAME|SURNAME)",
    "number": r"(?:(?:PASSPORT|DOCUMENT|ID|LICEN[CS]E)\s*(?:NO\.?|NUMBER))",
    "nationality": r"NATIONALITY",
    "dob": r"(?:DATE\s+OF\s+BIRTH|DOB)",
    "expiry": r"(?:DATE\s+OF\s+EXPIRY|EXPIRY|EXPIRATION\s+DATE)",
    "issue": r"(?:DATE\s+OF\s+ISSUE|ISSUE\s+DATE)",
    "gender": r"(?:SEX|GENDER)",
    "visa_number": r"VISA\s*(?:NO\.?|NUMBER)",
    "visa_type": r"VISA\s+TYPE",
    "valid_from": r"VALID\s+FROM",
    "valid_until": r"VALID\s+(?:UNTIL|TO)",
    "stay_duration": r"(?:DURATION\s+OF\s+STAY|STAY\s+DURATION)",
}


def extract_viz(lines: list[tuple[str, float | None]]) -> dict[str, FieldValue]:
    fields: dict[str, FieldValue] = {}
    for text, confidence in lines:
        for name, label in LABELS.items():
            match = re.fullmatch(rf"\s*{label}\s*[:\-]?\s+(.+?)\s*", text, re.I)
            if not match:
                continue
            raw = match.group(1)
            value = " ".join(raw.upper().split())
            if name in fields and (fields[name].confidence or 0) >= (confidence or 0):
                continue
            fields[name] = FieldValue(
                raw=raw,
                corrected=value,
                confidence=confidence,
                source="viz",
                corrections=["Uppercased and collapsed whitespace."]
                if raw != value
                else [],
            )
    return fields


def classify_text(text: str, hint: DocumentType = "unknown") -> DocumentType:
    if hint != "unknown":
        return hint
    upper = text.upper()
    for pattern, kind in [
        (r"\bVISA\b", "visa"),
        (r"\bDRIV(?:ING|ER)\b", "license"),
        (r"\bPERMIT\b", "permit"),
        (r"\bPASSPORT\b", "passport"),
        (r"\b(?:IDENTITY|NATIONAL\s+ID)\b", "id"),
    ]:
        if re.search(pattern, upper):
            return kind
    return "unknown"
