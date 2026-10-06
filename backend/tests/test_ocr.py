"""Actual image OCR smoke tests and transparent unavailable-engine behavior."""

from datetime import date

import numpy as np
import pytest
from app.demo import generate_document
from app.layers.l1_ocr.engine import configure_tesseract, extract_ocr
from app.layers.l1_ocr.viz import classify_text, extract_viz
from app.pipeline import analyze_phase1


def test_missing_engine_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.layers.l1_ocr.engine.configure_tesseract", lambda: None)
    result = extract_ocr(np.zeros((800, 1200, 3), dtype=np.uint8))
    assert result.status == "unavailable"
    assert not result.data.viz_fields


def test_viz_fields_are_independent_of_mrz():
    fields = extract_viz(
        [
            ("VISA NUMBER: TEST42", 0.8),
            ("VISA TYPE: TOURIST", 0.9),
            ("VALID FROM: 2026-01-01", 0.9),
            ("STAY DURATION: 30 DAYS", 0.9),
        ]
    )
    assert fields["visa_number"].corrected == "TEST42"
    assert fields["visa_type"].corrected == "TOURIST"
    assert "dob" not in fields


@pytest.mark.parametrize(
    "text,kind",
    [
        ("PASSPORT", "passport"),
        ("VISA", "visa"),
        ("NATIONAL ID", "id"),
        ("DRIVING LICENSE", "license"),
        ("ENTRY PERMIT", "permit"),
        ("unrecognized text", "unknown"),
    ],
)
def test_text_classification(text, kind):
    assert classify_text(text) == kind


@pytest.mark.ocr
@pytest.mark.skipif(configure_tesseract() is None, reason="Tesseract is not installed")
@pytest.mark.parametrize("variant", ["genuine", "dob_altered", "checksum_failed"])
def test_actual_image_to_validation(variant, db_url):
    payload, _ = generate_document(variant=variant)
    result = analyze_phase1(payload, date(2026, 10, 3), db_url=db_url)
    assert result.status == "ok"
    assert result.ocr.data.mrz is not None
    assert result.ocr.data.mrz.fields["number"].corrected == "Z9000000"
    assert result.ocr.data.mrz.fields["name"].corrected == "EXAMPLE ALEX"
    assert result.ocr.data.mrz.fields["gender"].corrected == "X"
    assert result.validation.data.mismatch_count == (
        1 if variant == "dob_altered" else 0
    )
    failed = [check for check in result.validation.data.checks if check.valid is False]
    assert len(failed) == (1 if variant == "checksum_failed" else 0)
