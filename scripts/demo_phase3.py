"""Analyze one image; optional artifacts are an explicit local-only export."""

import argparse
import base64
import json
from pathlib import Path

from app.layers.l3_tampering.analyzer import analyze_tampering


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--photo-region", help="Normalized JSON [x,y,width,height]")
    parser.add_argument(
        "--output", type=Path, help="Explicitly save image overlays here"
    )
    parser.add_argument("--no-cnn", action="store_true")
    args = parser.parse_args()
    region = json.loads(args.photo_region) if args.photo_region else None
    result = analyze_tampering(args.image.read_bytes(), region, not args.no_cnn)
    report = result.model_dump(mode="json")
    for key in ("heatmap_png_base64", "overlay_png_base64", "cnn_heatmap_png_base64"):
        value = report["data"].pop(key)
        if args.output and value:
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / (key.replace("_png_base64", "") + ".png")).write_bytes(
                base64.b64decode(value)
            )
    if args.output:
        (args.output / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
