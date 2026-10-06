"""Run genuine image OCR and validation without reading ground truth."""

import argparse
import json
from datetime import date
from pathlib import Path

from app.pipeline import analyze_phase1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--reference-date", type=date.fromisoformat, default=date(2026, 10, 3)
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze_phase1(args.image.read_bytes(), args.reference_date)
    # Do not dump large previews to the terminal or persist them by default.
    data = result.model_dump(
        mode="json", exclude={"capture": {"data": {"image_base64"}}}
    )
    rendered = json.dumps(data, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Synthetic demo report written to {args.output.resolve()}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
