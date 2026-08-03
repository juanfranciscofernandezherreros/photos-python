"""
conftest.py — shared fixtures for all tests.

Database: each test gets an isolated SQLite in-memory database injected
via db.set_engine(). Tables are created fresh for every test so tests
never interfere with each other or with ~/PhotosSync/data/.

Filesystem: ORGANIZED_DIR and THUMBS_DIR are redirected to tmp_path.
"""
from __future__ import annotations

import json
import os
import pytest
from pathlib import Path

import os as _os
_os.environ.setdefault("TESTING", "1")   # disables slowapi IP rate limiting in tests

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


# ── Fast password hashing in tests ────────────────────────────────────────────
# bcrypt is deliberately slow; running it for every fixture makes the suite
# crawl. Replace it with a plain (still-salted) sha256 for tests only.
@pytest.fixture(autouse=True, scope="session")
def _fast_password_hashing():
    import photos_sync.auth as _auth
    import hashlib, os

    def _fast_hash(plain: str) -> str:
        salt = os.urandom(8).hex()
        h = hashlib.sha256((salt + plain).encode()).hexdigest()
        return f"sha256${salt}${h}"

    _auth.hash_password = _fast_hash
    yield


@pytest.fixture(autouse=True)
def _clear_login_lockouts():
    """Reset the in-memory lockout state before each test so tests don't
    bleed into each other through the global _login_failures dict."""
    from photos_sync.web_server import _login_failures
    _login_failures.clear()
    yield
    _login_failures.clear()


# ── Database fixture ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def db_engine(tmp_path, monkeypatch):
    """Create a fresh SQLite in-memory engine for every test."""
    from photos_sync import db as db_mod

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_mod.init_db(engine)
    db_mod.set_engine(engine)

    yield engine

    # Tear down
    db_mod.metadata.drop_all(engine)
    engine.dispose()
    db_mod.set_engine(None)


# ── Filesystem fixture ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def cwd_temporal(tmp_path, monkeypatch, db_engine):
    """Redirect filesystem paths to tmp_path for isolation."""
    monkeypatch.chdir(tmp_path)

    import photos_sync.config as cfg
    monkeypatch.setattr(cfg, "ORGANIZED_DIR", tmp_path / "organizado")
    monkeypatch.setattr(cfg, "THUMBS_DIR", tmp_path / "thumbs")
    (tmp_path / "thumbs").mkdir(parents=True, exist_ok=True)

    # Patch ORGANIZED_DIR in pipeline modules that import it directly
    import photos_sync.pipeline.organize as organize_mod
    import photos_sync.pipeline.compress as compress_mod
    monkeypatch.setattr(organize_mod, "ORGANIZED_DIR", tmp_path / "organizado")
    if hasattr(compress_mod, "ORGANIZED_DIR"):
        monkeypatch.setattr(compress_mod, "ORGANIZED_DIR", tmp_path / "organizado")

    return tmp_path


# ── Helper fixtures ───────────────────────────────────────────────────────────

@pytest.fixture()
def metadatos_json(tmp_path):
    """Insert sample captures into the database and return their dicts."""
    from photos_sync import repository as repo

    datos = [
        {
            "id": "aaa-111",
            "archivo": "Screenshot_20231024_153020.png",
            "formato": "png",
            "tamano_mb": 1.2,
            "mtime": 1698158220.0,
            "fecha_captura": "2023-10-24 15:30:20",
            "ruta_original": str(tmp_path / "Screenshot_20231024_153020.png"),
        },
        {
            "id": "bbb-222",
            "archivo": "Screenshot_20231025_090000.jpg",
            "formato": "jpg",
            "tamano_mb": 0.8,
            "mtime": 1698224400.0,
            "fecha_captura": "2023-10-25 09:00:00",
            "ruta_original": str(tmp_path / "Screenshot_20231025_090000.jpg"),
        },
    ]
    repo.upsert_captures(datos)
    return datos


@pytest.fixture()
def carpeta_organizada(tmp_path, metadatos_json):
    """Create organized folder structure and update capture dest_paths."""
    from photos_sync import repository as repo

    destino = tmp_path / "organizado"
    updated = []
    for captura in metadatos_json:
        fecha = captura["fecha_captura"][:10]
        ano, mes, dia = fecha.split("-")
        carpeta = destino / ano / mes / dia
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = carpeta / captura["archivo"]
        archivo.write_bytes(b"fake image data")
        captura["ruta_destino"] = str(archivo)
        updated.append(captura)
    repo.upsert_captures(updated)
    return destino


@pytest.fixture()
def cliente_api(tmp_path):
    """Authenticated admin HTTP test client.

    Creates an admin via the setup endpoint (which also logs in), so all
    existing data/config endpoints work. The session cookie is kept by
    the TestClient across requests.
    """
    from fastapi.testclient import TestClient
    from photos_sync.web_server import app
    with TestClient(app, raise_server_exceptions=True) as c:
        # Bootstrap + auto-login the admin
        c.post("/api/auth/setup-admin",
               json={"username": "admin", "password": "admin12345"})
        yield c


@pytest.fixture()
def cliente_anon(tmp_path):
    """Unauthenticated client — for testing 401 responses."""
    from fastapi.testclient import TestClient
    from photos_sync.web_server import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def cliente_user(tmp_path):
    """Client logged in as a normal (non-admin) user — for testing 403."""
    from fastapi.testclient import TestClient
    from photos_sync.web_server import app
    with TestClient(app, raise_server_exceptions=True) as c:
        # First create the admin (needed to create other users)
        admin = TestClient(app)
        admin.post("/api/auth/setup-admin",
                   json={"username": "admin", "password": "admin12345"})
        admin.post("/api/users",
                   json={"username": "bob", "password": "bob12345", "role": "user"})
        # Now log in as bob on the returned client
        c.post("/api/auth/login", json={"username": "bob", "password": "bob12345"})
        yield c
