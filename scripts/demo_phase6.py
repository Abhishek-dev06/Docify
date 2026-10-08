"""Generate and run the three fictional five-minute walkthrough cases."""

import argparse
import json
import os
from datetime import date
from pathlib import Path

import cv2
from app.demo_cases import PHOTO_REGION, demo_case
from app.screening import screen_document
from app.settings import ROOT
from app.storage.database import seed_mock_database
from demo_phase4 import compact_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--scenario",
        choices=["all", "genuine", "photo_replaced", "dob_altered"],
        default="all",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "phase6_demo")
    args = parser.parse_args()
    cv2.setNumThreads(2)
    os.environ["OMP_THREAD_LIMIT"] = "2"
    args.output.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{(args.output.resolve() / 'mock.db').as_posix()}"
    seed_mock_database(db_url)
    cases = ["genuine", "photo_replaced", "dob_altered"]
    for name in cases if args.scenario == "all" else [args.scenario]:
        document, live, truth = demo_case(name)
        (args.output / f"{name}_document.png").write_bytes(document)
        (args.output / f"{name}_live.png").write_bytes(live)
        (args.output / f"{name}_truth.json").write_text(
            json.dumps(truth, indent=2), encoding="utf-8"
        )
        if args.prepare_only:
            print(f"Prepared fictional {name} in {args.output}")
            continue
        result = screen_document(
            document, date(2026, 10, 3), "passport", live, PHOTO_REGION, db_url=db_url
        )
        (args.output / f"{name}_result.json").write_text(
            json.dumps(compact_result(result), indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "scenario": name,
                    "status": result.status,
                    "score": result.risk.data.score,
                    "category": result.risk.data.category,
                    "face": result.face.data.decision if result.face else None,
                    "mismatch_count": result.validation.data.mismatch_count
                    if result.validation
                    else None,
                    "missing_required": result.risk.data.missing_required_signals,
                    "duration_ms": result.duration_ms,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
