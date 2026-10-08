"""ICAO TD1/TD2/TD3 parser with conservative, position-based OCR correction."""

import re

from app.schemas.common import FieldValue
from app.schemas.documents import CheckDigit, MRZData

NUMERIC_CONFUSIONS = str.maketrans({"O": "0", "I": "1", "B": "8"})
ALPHA_CONFUSIONS = str.maketrans({"0": "O", "1": "I", "8": "B"})


def check_digit(value: str) -> str:
    """Apply the ICAO 7-3-1 repeating weights; filler has value zero."""
    total = 0
    for index, character in enumerate(value):
        if character == "<":
            number = 0
        elif "0" <= character <= "9":
            number = int(character)
        elif "A" <= character <= "Z":
            number = ord(character) - ord("A") + 10
        else:
            raise ValueError(f"Invalid MRZ character: {character!r}")
        total += number * (7, 3, 1)[index % 3]
    return str(total % 10)


def _clean(line: str) -> str:
    return re.sub(r"\s+", "", line.upper())


def parse_mrz(lines: list[str], confidence: float | None = None) -> MRZData:
    """Never pad/truncate a line or change alphanumeric data to force a checksum."""
    raw = list(lines)
    cleaned = [_clean(line) for line in lines]
    sizes = tuple(map(len, cleaned))
    formats = {(30, 30, 30): "TD1", (36, 36): "TD2", (44, 44): "TD3"}
    if sizes not in formats:
        raise ValueError("Expected TD1 (3x30), TD2 (2x36), or TD3 (2x44) MRZ.")
    fmt = formats[sizes]
    if any(re.search(r"[^A-Z0-9<]", line) for line in cleaned):
        raise ValueError(
            "MRZ contains unsupported characters; rescan instead of guessing."
        )
    if cleaned[0].startswith("V"):
        raise ValueError("MRV-A/MRV-B visa MRZ is not TD3/TD2; use VIZ extraction.")
    corrected = [list(line) for line in cleaned]
    corrections: list[str] = []
    if raw != cleaned:
        corrections.append("Whitespace removed and characters uppercased for parsing.")

    def correct(line: int, start: int, end: int, alphabetic: bool = False) -> None:
        table = ALPHA_CONFUSIONS if alphabetic else NUMERIC_CONFUSIONS
        for position in range(start, end):
            old = corrected[line][position]
            new = old.translate(table)
            if old != new:
                corrected[line][position] = new
                corrections.append(
                    f"Line {line + 1}, column {position + 1}: {old}->{new} "
                    f"({'alphabetic' if alphabetic else 'numeric'} field)."
                )

    correct(0, 2, 5, True)
    if fmt == "TD1":
        for a, b in [(0, 7), (8, 15), (29, 30)]:
            correct(1, a, b)
        correct(0, 14, 15)
        correct(1, 15, 18, True)
        correct(2, 0, 30, True)
        positions = {
            "number": (0, 5, 14),
            "issuing_country": (0, 2, 5),
            "nationality": (1, 15, 18),
            "dob": (1, 0, 6),
            "expiry": (1, 8, 14),
            "gender": (1, 7, 8),
            "name": (2, 0, 30),
        }
    else:
        for a, b in [(9, 10), (13, 20), (21, 28)]:
            correct(1, a, b)
        correct(1, 10, 13, True)
        correct(0, 5, sizes[0], True)
        correct(1, sizes[1] - 1, sizes[1])
        if fmt == "TD3":
            correct(1, 42, 43)
        positions = {
            "number": (1, 0, 9),
            "issuing_country": (0, 2, 5),
            "nationality": (1, 10, 13),
            "dob": (1, 13, 19),
            "expiry": (1, 21, 27),
            "gender": (1, 20, 21),
            "name": (0, 5, sizes[0]),
        }
    out = ["".join(line) for line in corrected]
    fields: dict[str, FieldValue] = {}
    for name, (line, start, end) in positions.items():
        before, after = cleaned[line][start:end], out[line][start:end]
        value = " ".join(after.replace("<", " ").split())
        if name == "gender" and after == "<":
            value = "X"
        fields[name] = FieldValue(
            raw=before,
            corrected=value,
            confidence=confidence,
            source="mrz",
            corrections=(
                [f"Position-constrained OCR correction: {before} -> {after}"]
                if before != after
                else []
            ),
        )
    checks: list[CheckDigit] = []
    limitations: list[str] = []

    def add(name: str, value: str, observed: str, optional: bool = False) -> None:
        expected = check_digit(value)
        # A filler digit is allowed for an unused TD3 optional-data field.
        unused = optional and set(value) <= {"<"} and observed == "<"
        checks.append(
            CheckDigit(
                field=name,
                input=value,
                observed=observed,
                expected=expected,
                valid=unused or observed == expected,
            )
        )

    if fmt == "TD1":
        a, b, _ = out
        add("number", a[5:14], a[14])
        add("dob", b[0:6], b[6])
        add("expiry", b[8:14], b[14])
        add("composite", a[5:30] + b[0:7] + b[8:15] + b[18:29], b[29])
        extended = a[14] == "<"
    else:
        b = out[1]
        add("number", b[:9], b[9])
        add("dob", b[13:19], b[19])
        add("expiry", b[21:27], b[27])
        if fmt == "TD3":
            add("optional_data", b[28:42], b[42], optional=True)
            add("composite", b[:10] + b[13:20] + b[21:43], b[43])
        else:
            add("composite", b[:10] + b[13:20] + b[21:35], b[35])
        extended = b[9] == "<"
    if extended:
        limitations.append(
            "Extended document number detected; number reconstruction is unsupported."
        )
        checks[0].valid = None
        checks[0].expected = None
        fields["number"].corrected = None
    if not re.fullmatch(r"[A-Z<]+", out[0][:2]):
        limitations.append("Document code is malformed.")
    sex_line, sex_start, sex_end = positions["gender"]
    if out[sex_line][sex_start:sex_end] not in {"M", "F", "<"}:
        limitations.append("Sex marker is not M, F or filler; inspect the OCR.")
    return MRZData(
        format=fmt,
        raw_lines=raw,
        corrected_lines=out,
        fields=fields,
        checks=checks,
        corrections=corrections,
        limitations=limitations,
    )


def find_mrz(text: str, confidence: float | None = None) -> MRZData | None:
    lines = [line for line in text.splitlines() if _clean(line)]
    for index in range(len(lines)):
        for count, length in [(3, 30), (2, 44), (2, 36)]:
            candidate = lines[index : index + count]
            if len(candidate) != count or any(
                len(_clean(x)) != length for x in candidate
            ):
                continue
            first = _clean(candidate[0])
            if first[0] not in "PACI" or "<" not in first:
                continue
            try:
                return parse_mrz(candidate, confidence)
            except ValueError:
                continue
    return None
