from __future__ import annotations

import pytest

from photos_sync.runtime_secrets import (
    get_app_secret_key,
    get_database_url,
    read_secret,
)


def test_secret_file_takes_precedence(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("from-file\n", encoding="utf-8")
    monkeypatch.setenv("EXAMPLE_SECRET", "from-environment")
    monkeypatch.setenv("EXAMPLE_SECRET_FILE", str(secret_file))

    assert read_secret("EXAMPLE_SECRET") == "from-file"


def test_missing_secret_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("EXAMPLE_SECRET_FILE", str(tmp_path / "missing"))

    with pytest.raises(RuntimeError, match="Cannot read"):
        read_secret("EXAMPLE_SECRET")


@pytest.mark.parametrize("value", ["short", "change-me-in-env-file"])
def test_weak_session_secret_is_rejected(monkeypatch, value):
    monkeypatch.delenv("SECRET_KEY_FILE", raising=False)
    monkeypatch.setenv("SECRET_KEY", value)
    monkeypatch.setenv("TESTING", "0")

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        get_app_secret_key()


def test_database_url_encodes_password_from_file(monkeypatch, tmp_path):
    password_file = tmp_path / "postgres.txt"
    password_file.write_text("a:b/@ value\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", str(password_file))
    monkeypatch.setenv("POSTGRES_HOST", "db")

    assert get_database_url() == (
        "postgresql://photos:a%3Ab%2F%40+value@db:5432/photos_sync"
    )
