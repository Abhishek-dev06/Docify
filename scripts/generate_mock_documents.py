"""Generate a deterministic synthetic-only Phase 1 demo set."""

import argparse
import json
from pathlib import Path

from app.demo import SyntheticIdentity, generate_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/synthetic"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for variant in (
        "genuine",
        "dob_altered",
        "checksum_failed",
        "blurred",
        "perspective",
    ):
        payload, truth = generate_document(variant=variant)
        (args.output / f"{variant}.png").write_bytes(payload)
        (args.output / f"{variant}.json").write_text(
            json.dumps(truth, indent=2), encoding="utf-8"
        )
    for name, identity in [
        ("blacklisted", SyntheticIdentity(number="Z9000001")),
        ("previously_seen", SyntheticIdentity(number="Z9000002")),
        ("expired", SyntheticIdentity(expiry="2020-10-03", issue="2010-10-04")),
    ]:
        payload, truth = generate_document(identity)
        truth["variant"] = name
        (args.output / f"{name}.png").write_bytes(payload)
        (args.output / f"{name}.json").write_text(
            json.dumps(truth, indent=2), encoding="utf-8"
        )
    print(
        "Created 8 fictional images and ground-truth JSON files in "
        f"{args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
