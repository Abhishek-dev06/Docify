"""Central configuration with project-relative defaults."""

import os
import tempfile
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def serverless_runtime() -> bool:
    """Return true only for explicitly detected serverless deployments."""
    return bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def runtime_data_dir() -> Path:
    """Choose a writable default while allowing a persistent host override."""
    configured = os.getenv("APP_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if serverless_runtime():
        return Path(tempfile.gettempdir()) / "docify"
    return ROOT / "data"


def load_config(name: str) -> dict:
    with (ROOT / "config" / name).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def database_url() -> str:
    default = f"sqlite:///{(runtime_data_dir() / 'screening.db').as_posix()}"
    return os.getenv("SCREENING_DATABASE_URL", default)


def audit_database_url() -> str:
    default = f"sqlite:///{(runtime_data_dir() / 'audit.db').as_posix()}"
    return os.getenv("AUDIT_DATABASE_URL", default)


def allowed_origins() -> list[str]:
    return [
        value.strip().rstrip("/")
        for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    ]


def audit_is_persistent() -> bool:
    configured = os.getenv("AUDIT_PERSISTENT")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return not serverless_runtime()
