"""Run complete screening; JSON exports omit all document and heatmap images."""

import argparse
import json
from datetime import date
from pathlib import Path

from app.screening import ScreeningResult, screen_document


def compact_result(result: ScreeningResult) -> dict:
    data = result.model_dump(mode="json")
    data["capture"]["data"].pop("image_base64", None)
    if data["tampering"]:
        for key in (
            "heatmap_png_base64",
            "overlay_png_base64",
            "cnn_heatmap_png_base64",
        ):
            data["tampering"]["data"].pop(key, None)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--live", type=Path)
    parser.add_argument("--reference-date", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--document-type",
        default="unknown",
        choices=["passport", "visa", "id", "license", "permit", "unknown"],
    )
    parser.add_argument("--photo-region", help="Normalized JSON [x,y,width,height]")
    parser.add_argument("--output", type=Path, help="Explicitly export image-free JSON")
    args = parser.parse_args()
    result = screen_document(
        args.document.read_bytes(),
        args.reference_date,
        args.document_type,
        args.live.read_bytes() if args.live else None,
        json.loads(args.photo_region) if args.photo_region else None,
    )
    data = compact_result(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
