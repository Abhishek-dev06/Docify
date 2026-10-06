"""Measure only the generated Phase 1 development fixtures, not real accuracy."""

import json
import statistics
from datetime import date

from app.pipeline import analyze_phase1
from app.settings import ROOT


def main() -> None:
    rows = []
    for path in sorted((ROOT / "data" / "synthetic").glob("*.png")):
        truth = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        result = analyze_phase1(path.read_bytes(), date(2026, 10, 3))
        data = result.ocr.data if result.ocr else None
        validation = result.validation
        comparisons = {}
        for field in ("name", "number", "nationality", "dob", "expiry", "gender"):
            observed = data.viz_fields.get(field) if data else None
            comparisons[field] = bool(
                observed and observed.corrected == truth["viz_fields"][field]
            )
        row = {
            "scenario": path.stem,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "mrz_format": data.mrz.format if data and data.mrz else None,
            "mrz_checks": {c.field: c.valid for c in validation.data.checks}
            if validation
            else {},
            "mismatch_count": validation.data.mismatch_count if validation else None,
            "findings": [f.code for f in validation.findings] if validation else [],
            "viz_field_matches": comparisons,
        }
        rows.append(row)
        print(
            f"{path.stem}: {result.status}, mismatches={row['mismatch_count']}, "
            f"{result.duration_ms:.0f} ms"
        )
    if not rows:
        raise SystemExit("Generate the synthetic fixtures first.")
    report = {
        "scope": "Synthetic development fixtures; not real-world accuracy.",
        "reference_date": "2026-10-03",
        "sample_count": len(rows),
        "mean_latency_ms": round(statistics.mean(r["duration_ms"] for r in rows), 2),
        "median_latency_ms": round(
            statistics.median(r["duration_ms"] for r in rows), 2
        ),
        "scenarios": rows,
    }
    out = ROOT / "reports" / "phase1_smoke.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
