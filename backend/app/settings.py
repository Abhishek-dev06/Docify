"""Central configuration with project-relative defaults."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def load_config(name: str) -> dict:
    with (ROOT / "config" / name).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def database_url() -> str:
    default = f"sqlite:///{(ROOT / 'data' / 'screening.db').as_posix()}"
    return os.getenv("SCREENING_DATABASE_URL", default)
