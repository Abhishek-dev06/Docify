"""Central configuration with project-relative defaults."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Vercel functions cannot write to the deployed bundle; use its writable temp
# directory for the demo's optional SQLite state.
DATA_ROOT = Path("/tmp/docify") if os.getenv("VERCEL") else ROOT / "data"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def load_config(name: str) -> dict:
    with (ROOT / "config" / name).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def database_url() -> str:
    default = f"sqlite:///{(DATA_ROOT / 'screening.db').as_posix()}"
    return os.getenv("SCREENING_DATABASE_URL", default)
