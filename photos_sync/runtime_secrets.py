"""Secure runtime configuration loaded from environment variables or files."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

_PLACEHOLDER_SECRETS = {
    "change-me-in-env-file",
    "cambia-esto-por-una-clave-larga-y-aleatoria-de-64-caracteres",
}


def read_secret(name: str, *, required: bool = False) -> str | None:
    """Read ``NAME_FILE`` first, then ``NAME``, without silently falling back."""
    file_name = os.getenv(f"{name}_FILE", "").strip()
    if file_name:
        path = Path(file_name)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Cannot read {name}_FILE at {path}: {exc}") from exc
    else:
        value = os.getenv(name, "").strip()

    if required and not value:
        raise RuntimeError(f"{name} or {name}_FILE must be configured")
    return value or None


def get_app_secret_key() -> str:
    """Return a strong session key, failing closed outside the test suite."""
    value = read_secret("SECRET_KEY")
    if os.getenv("TESTING", "0") == "1" and not value:
        return "tests-only-session-secret-key-32-bytes-minimum"
    if not value:
        raise RuntimeError("SECRET_KEY or SECRET_KEY_FILE must be configured")
    if value.lower() in _PLACEHOLDER_SECRETS or len(value.encode("utf-8")) < 32:
        raise RuntimeError("SECRET_KEY must be a non-placeholder value of at least 32 bytes")
    return value


def get_database_url() -> str:
    """Build the database URL while keeping its password in a mounted file."""
    explicit = read_secret("DATABASE_URL")
    if explicit:
        return explicit

    password = read_secret("POSTGRES_PASSWORD")
    if password:
        user = os.getenv("POSTGRES_USER", "photos")
        host = os.getenv("POSTGRES_HOST", "db")
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        database = os.getenv("POSTGRES_DB", "photos_sync")
        return (
            f"postgresql://{quote_plus(user)}:{quote_plus(password)}@"
            f"{host}:{port}/{quote_plus(database)}"
        )

    return "postgresql://localhost/photos_sync"
