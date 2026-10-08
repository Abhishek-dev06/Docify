"""Generate clearly synthetic tamper examples with grouped train/val/test splits."""

import argparse
from pathlib import Path

from app.layers.l3_tampering.synthetic import generate_dataset
from app.settings import ROOT

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "tampering")
    parser.add_argument("--bases", type=int, default=100)
    args = parser.parse_args()
    if not 20 <= args.bases <= 10000:
        parser.error("Use between 20 and 10000 base cards.")
    records = generate_dataset(args.output, args.bases)
    print({s: sum(r["split"] == s for r in records) for s in ("train", "val", "test")})
