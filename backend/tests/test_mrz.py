"""Known examples and adversarial MRZ parsing cases."""

import pytest
from app.demo import SyntheticIdentity, build_mrz
from app.layers.l1_ocr.mrz import check_digit, find_mrz, parse_mrz


def test_icao_td3_example():
    # Public fictional example from ICAO Doc 9303.
    result = parse_mrz(
        [
            "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
            "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
        ]
    )
    assert all(check.valid for check in result.checks)
    assert result.fields["number"].corrected == "L898902C3"
    assert result.fields["name"].corrected == "ERIKSSON ANNA MARIA"


def test_icao_td1_example():
    result = parse_mrz(
        [
            "I<UTOD231458907<<<<<<<<<<<<<<<",
            "7408122F1204159UTO<<<<<<<<<<<6",
            "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
        ]
    )
    assert all(check.valid for check in result.checks)


@pytest.mark.parametrize(
    "fmt,width,count", [("TD1", 30, 3), ("TD2", 36, 2), ("TD3", 44, 2)]
)
def test_generated_mrz_formats(fmt, width, count):
    lines = build_mrz(SyntheticIdentity(), fmt)
    assert list(map(len, lines)) == [width] * count
    result = parse_mrz(lines)
    assert result.format == fmt
    assert all(check.valid for check in result.checks)
    assert result.fields["dob"].corrected == "880412"


@pytest.mark.parametrize(
    "value,expected", [("", "0"), ("<<<<", "0"), ("520727", "3"), ("L898902C3", "6")]
)
def test_known_check_digits(value, expected):
    assert check_digit(value) == expected


def test_numeric_corrections_preserve_raw():
    lines = build_mrz(SyntheticIdentity())
    lines[1] = lines[1][:13] + "BBO4I2" + lines[1][19:]
    result = parse_mrz(lines)
    assert result.raw_lines == lines
    assert result.fields["dob"].raw == "BBO4I2"
    assert result.fields["dob"].corrected == "880412"
    assert result.fields["dob"].corrections
    assert all(check.valid for check in result.checks)


def test_bad_checksum_is_not_repaired():
    lines = build_mrz(SyntheticIdentity())
    lines[1] = lines[1][:-1] + str((int(lines[1][-1]) + 1) % 10)
    result = parse_mrz(lines)
    assert result.checks[-1].valid is False
    assert result.corrected_lines == lines


def test_alphanumeric_document_number_is_not_guessed():
    lines = build_mrz(SyntheticIdentity(number="Z9000080"))
    lines[1] = lines[1][:6] + "B" + lines[1][7:]
    result = parse_mrz(lines)
    assert "B" in result.fields["number"].corrected
    assert result.checks[0].valid is False


def test_unsupported_extended_number_is_unknown():
    lines = build_mrz(SyntheticIdentity(), "TD1")
    lines[0] = lines[0][:14] + "<" + lines[0][15:]
    result = parse_mrz(lines)
    assert result.fields["number"].corrected is None
    assert result.checks[0].valid is None
    assert result.limitations


def test_no_padding_or_truncation():
    lines = build_mrz(SyntheticIdentity())
    with pytest.raises(ValueError):
        parse_mrz([lines[0], lines[1][:-1]])


def test_visa_mrz_is_not_misparsed_as_passport():
    lines = build_mrz(SyntheticIdentity())
    lines[0] = "V" + lines[0][1:]
    with pytest.raises(ValueError, match="MRV"):
        parse_mrz(lines)


def test_find_mrz_in_ocr_noise():
    lines = build_mrz(SyntheticIdentity())
    assert find_mrz("HEADER\n" + "\n".join(lines) + "\nFOOTER").format == "TD3"


def test_invalid_character_rejected():
    with pytest.raises(ValueError):
        check_digit("ABC?")


def test_unspecified_sex_preserves_filler_and_normalizes_value():
    result = parse_mrz(build_mrz(SyntheticIdentity(gender="X")))
    assert result.fields["gender"].raw == "<"
    assert result.fields["gender"].corrected == "X"
    assert not result.limitations


def test_nonstandard_sex_marker_is_flagged():
    lines = build_mrz(SyntheticIdentity())
    lines[1] = lines[1][:20] + "K" + lines[1][21:]
    result = parse_mrz(lines)
    assert any("Sex marker" in limitation for limitation in result.limitations)
