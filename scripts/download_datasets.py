"""List official sources or download one selected file with byte cap and checksum."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from app.settings import ROOT


def download(
    url: str,
    destination: Path,
    expected_md5: str,
    max_bytes: int,
    minimum_bytes: int = 0,
) -> dict:
    if minimum_bytes > max_bytes:
        raise ValueError(
            "File exceeds configured byte budget; increase --max-mib explicitly."
        )
    if destination.exists():
        raise ValueError("Destination exists; choose an empty destination.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    if partial.exists():
        raise ValueError("Partial file already exists; choose an empty destination.")
    count, digest, sha = 0, hashlib.md5(usedforsecurity=False), hashlib.sha256()
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "SyntheticDocDemo/0.1"}
        )
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            partial.open("xb") as handle,
        ):
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise ValueError("Remote Content-Length exceeds byte budget.")
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > max_bytes:
                    raise ValueError("Download exceeded byte budget.")
                digest.update(chunk)
                sha.update(chunk)
                handle.write(chunk)
        if digest.hexdigest() != expected_md5 or count < minimum_bytes:
            raise ValueError(
                "Downloaded file failed publisher checksum/size validation."
            )
        partial.replace(destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return {
        "file": str(destination),
        "bytes": count,
        "sha256": sha.hexdigest(),
        "publisher_md5": digest.hexdigest(),
        "url": url,
    }


def main() -> None:
    catalog = json.loads((ROOT / "config" / "datasets.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=sorted(catalog))
    parser.add_argument(
        "--file", help="Exact filename from the catalog; omit to list only."
    )
    parser.add_argument("--max-mib", type=int, default=256)
    parser.add_argument("--output", type=Path, default=ROOT / "datasets" / "raw")
    args = parser.parse_args()
    entry = catalog[args.dataset]
    if args.file is None:
        print(json.dumps(entry, indent=2))
        return
    if args.file not in entry["files"] or args.max_mib <= 0:
        parser.error("Choose a listed file and a positive download budget.")
    asset = entry["files"][args.file]
    result = download(
        asset["url"],
        args.output / args.dataset / args.file,
        asset["md5"],
        args.max_mib * 1024**2,
        asset["minimum_bytes"],
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
