"""Download pinned OpenCV Zoo model bytes and verify their SHA-256 digests."""

import hashlib
import json
import os
import urllib.request
from pathlib import Path

from app.settings import ROOT


def main() -> None:
    manifest = json.loads((ROOT / "models" / "manifest.json").read_text())
    destination = Path(os.getenv("FACE_MODEL_DIR", ROOT / "models"))
    destination.mkdir(parents=True, exist_ok=True)
    for key, model in manifest.items():
        target = destination / model["filename"]
        if (
            target.is_file()
            and hashlib.sha256(target.read_bytes()).hexdigest() == model["sha256"]
        ):
            print(f"{key}: already verified")
        else:
            request = urllib.request.Request(
                model["url"], headers={"User-Agent": "SyntheticScreening/0.2"}
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read(model["size"] + 1)
            if (
                len(payload) != model["size"]
                or hashlib.sha256(payload).hexdigest() != model["sha256"]
            ):
                raise RuntimeError(
                    f"Integrity check failed for {key}; existing model preserved."
                )
            temporary = target.with_suffix(".download")
            temporary.write_bytes(payload)
            temporary.replace(target)
            print(f"{key}: downloaded and SHA-256 verified ({len(payload)} bytes)")
        license_path = destination / f"{key}-LICENSE.txt"
        if not license_path.exists():
            with urllib.request.urlopen(model["license_url"], timeout=30) as response:
                license_path.write_bytes(response.read(64 * 1024))


if __name__ == "__main__":
    main()
