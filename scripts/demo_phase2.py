"""Run one-to-one face matching and limited still-image liveness diagnostics."""

import argparse
import json
from pathlib import Path

from app.layers.l0_capture.preprocess import decode_image
from app.layers.l4_face.liveness import evaluate_liveness
from app.layers.l4_face.verification import verify_faces


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("live", type=Path)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    document = decode_image(args.document.read_bytes())
    live = decode_image(args.live.read_bytes())
    results = {
        "verification": verify_faces(document, live, args.threshold).model_dump(
            mode="json"
        ),
        "liveness": evaluate_liveness([live]).model_dump(mode="json"),
    }
    rendered = json.dumps(results, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Report written to {args.output.resolve()}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
