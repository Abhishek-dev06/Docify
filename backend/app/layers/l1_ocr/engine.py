"""Tesseract adapter with explicit engine failure and bounded runtime."""

import csv
import io
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from app.layers.l1_ocr.mrz import find_mrz
from app.layers.l1_ocr.viz import classify_text, extract_viz
from app.schemas.common import DocumentType, Finding, LayerResult
from app.schemas.documents import OCRData
from app.settings import ROOT


def configure_tesseract() -> str | None:
    candidates = [
        os.getenv("TESSERACT_CMD"),
        shutil.which("tesseract"),
        str(ROOT / ".tools" / "tesseract" / "tesseract.exe"),
        str(ROOT / ".tools" / "ocr" / "Library" / "bin" / "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _read(image: np.ndarray, config: str) -> list[tuple[str, float | None]]:
    executable = configure_tesseract()
    if executable is None:
        raise OSError("Tesseract is unavailable.")
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Cannot encode the OCR input.")
    executable_path = Path(executable)
    data_dir = os.getenv("TESSDATA_PREFIX")
    if not data_dir:
        for directory in (
            executable_path.parent / "tessdata",
            executable_path.parents[2] / "share" / "tessdata",
            executable_path.parent.parent / "share" / "tessdata",
        ):
            if directory.is_dir():
                data_dir = str(directory)
                break
    data_args = ["--tessdata-dir", data_dir] if data_dir else []
    # stdin/stdout avoid temporary image files, including wrapper-created files.
    result = subprocess.run(
        [
            executable,
            "stdin",
            "stdout",
            "-l",
            os.getenv("OCR_LANGUAGE", "eng"),
            *data_args,
            *shlex.split(config),
            "-c",
            "tessedit_create_tsv=1",
        ],
        input=encoded.tobytes(),
        capture_output=True,
        check=True,
        timeout=float(os.getenv("OCR_TIMEOUT_SECONDS", "20")),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    data = csv.DictReader(
        io.StringIO(result.stdout.decode("utf-8")),
        delimiter="\t",
        quoting=csv.QUOTE_NONE,
    )
    groups: dict[tuple, list[tuple[str, float]]] = {}
    for row in data:
        word = row.get("text", "")
        if not word.strip():
            continue
        key = tuple(row[k] for k in ("page_num", "block_num", "par_num", "line_num"))
        groups.setdefault(key, []).append((word, float(row["conf"])))
    lines = []
    for words in groups.values():
        scores = [score / 100 for _, score in words if score >= 0]
        lines.append(
            (
                " ".join(word for word, _ in words),
                sum(scores) / len(scores) if scores else None,
            )
        )
    return lines


def _read_mrz_rows(image: np.ndarray) -> list[tuple[str, float | None]]:
    """Find long text bands in the lower half; raw-line OCR preserves fillers."""
    height, width = image.shape[:2]
    margin = max(1, int(width * 0.025))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = gray[:, margin : width - margin] < 150
    active = np.mean(mask, axis=1) > 0.02
    active[: int(height * 0.55)] = False
    transitions = np.diff(np.r_[False, active, False].astype(int))
    bands = []
    for start, end in zip(
        np.where(transitions == 1)[0], np.where(transitions == -1)[0], strict=True
    ):
        if not 8 <= end - start <= height * 0.08:
            continue
        columns = np.where(mask[start:end].any(axis=0))[0]
        if len(columns) and columns[-1] - columns[0] > width * 0.65:
            left = max(0, columns[0] + margin - 10)
            right = min(width, columns[-1] + margin + 11)
            row = image[max(0, start - 10) : min(height, end + 10)]
            bands.append((row[:, left:right], row))
    lines = []
    config = "--psm 13 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
    for band, full_row in bands[-3:]:
        recognized = _read(band, config)
        if recognized and "<" in recognized[0][0]:
            compact = "".join(recognized[0][0].split())
            if len(compact) not in {30, 36, 44}:
                # Different whitespace context can preserve repeated fillers.
                # Keep both raw readings; never invent missing characters.
                alternatives = _read(full_row, config)
                lines.extend(alternatives)
                # A different segmentation mode can recover repeated filler glyphs.
                # Preserve every reading and accept only observed exact-length rows.
                if not any(
                    len("".join(text.split())) in {30, 36, 44}
                    for text, _ in alternatives
                ):
                    lines.extend(_read(band, config.replace("--psm 13", "--psm 7")))
        lines.extend(recognized)
    return lines


def extract_ocr(
    image: np.ndarray, document_type: DocumentType = "unknown"
) -> LayerResult[OCRData]:
    started = time.perf_counter()
    if configure_tesseract() is None:
        return LayerResult(
            status="unavailable",
            data=OCRData(document_type=document_type),
            findings=[
                Finding(
                    code="OCR_ENGINE_MISSING",
                    explanation=(
                        "Install Tesseract and set TESSERACT_CMD or add it to PATH."
                    ),
                )
            ],
        )
    findings: list[Finding] = []
    try:
        lines = _read(image, "--psm 6")
        raw_text = "\n".join(line for line, _ in lines)
        row_lines = _read_mrz_rows(image)
        row_text = "\n".join(line for line, _ in row_lines)
        scores = [score for _, score in row_lines if score is not None]
        mrz = find_mrz(row_text, min(scores) if scores else None)
        # Discard only unsupported-length candidates for parsing, not raw evidence.
        if mrz is None:
            filtered = [
                line
                for line, _ in row_lines
                if len("".join(line.split())) in {30, 36, 44}
            ]
            mrz = find_mrz("\n".join(filtered), min(scores) if scores else None)
        if mrz is None:
            # Combine observed lines only; every source reading stays in raw_text.
            for count, width in ((2, 44), (2, 36), (3, 30)):
                headers = [
                    line
                    for line, _ in lines
                    if len("".join(line.split())) == width and line[:1] in "PACI"
                ]
                body = [
                    line for line, _ in row_lines if len("".join(line.split())) == width
                ]
                if headers and len(body) >= count - 1:
                    candidate = [headers[0], *body[-(count - 1) :]]
                    mrz = find_mrz(
                        "\n".join(candidate), min(scores) if scores else None
                    )
                    if mrz is not None:
                        break
        if mrz is None:
            mrz = find_mrz(raw_text)
        raw_text += "\n\n[MRZ row OCR]\n" + row_text
        # Retry a dedicated lower-document crop, preserving the original full OCR.
        if mrz is None:
            crop = image[int(image.shape[0] * 0.60) :, :]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=1.5, fy=1.5)
            mrz_lines = _read(
                gray,
                "--psm 6 -c "
                "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<",
            )
            mrz_text = "\n".join(line for line, _ in mrz_lines)
            scores = [score for _, score in mrz_lines if score is not None]
            mrz = find_mrz(mrz_text, min(scores) if scores else None)
            raw_text += "\n\n[MRZ crop OCR]\n" + mrz_text
        if mrz is not None and all(x.confidence is None for x in mrz.fields.values()):
            # Line-level confidence is a proxy, not a calibrated probability.
            scores = [
                score for line, score in lines if "<" in line and score is not None
            ]
            for field in mrz.fields.values():
                field.confidence = min(scores) if scores else None
        viz_fields = extract_viz(lines)
        kind = classify_text(raw_text, document_type)
        if kind == "unknown" and mrz is not None:
            kind = "passport" if mrz.format == "TD3" else "id"
        if mrz is None:
            findings.append(
                Finding(
                    code="MRZ_NOT_EXTRACTED",
                    severity="medium",
                    explanation=(
                        "No supported MRZ extracted; it may be absent or unreadable."
                    ),
                )
            )
        if mrz and mrz.corrections:
            findings.append(
                Finding(
                    code="OCR_CORRECTIONS",
                    severity="low",
                    explanation=(
                        "Position-constrained corrections were applied; "
                        "inspect raw and corrected text."
                    ),
                )
            )
        if not viz_fields:
            findings.append(
                Finding(
                    code="VIZ_NOT_EXTRACTED",
                    explanation=(
                        "No supported English label/value fields found; "
                        "cross-checks are unavailable."
                    ),
                )
            )
        return LayerResult(
            status="ok" if mrz or viz_fields else "insufficient_evidence",
            data=OCRData(
                document_type=kind, raw_text=raw_text, mrz=mrz, viz_fields=viz_fields
            ),
            findings=findings,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except (subprocess.SubprocessError, RuntimeError, OSError):
        return LayerResult(
            status="unavailable",
            data=OCRData(document_type=document_type),
            findings=[
                Finding(
                    code="OCR_ENGINE_FAILED",
                    explanation=(
                        "OCR failed or timed out. Check the executable, "
                        "language data and timeout."
                    ),
                )
            ],
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
