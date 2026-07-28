"""
conftest.py — shared fixtures for all tests.

Each test receives an isolated temporary directory as cwd, so that
JSON config files (conexiones_ssh.json, destino_guardado.json, etc.)
do not mix between tests or with the real project.
"""
import json
import os
import time
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def cwd_temporal(tmp_path, monkeypatch):
    """Changes the cwd to a temporary directory per test.
    All modules that open relative files (folders.py, ssh_connection.py,
    connection.py...) will write here without contaminating anything."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def metadatos_json(tmp_path):
    """Creates a minimal metadatos_screenshots.json and returns its path."""
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
    p = tmp_path / "metadatos_screenshots.json"
    p.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture()
def carpeta_organizada(tmp_path, metadatos_json):
    """Creates the organized folder structure (YYYY/MM/DD) and creates
    the physical files referenced in metadata, needed for compression."""
    import json as _json
    datos = _json.loads(metadatos_json.read_text())
    destino = tmp_path / "organizado"
    for captura in datos:
        fecha = captura["fecha_captura"][:10]
        ano, mes, dia = fecha.split("-")
        carpeta = destino / ano / mes / dia
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = carpeta / captura["archivo"]
        archivo.write_bytes(b"fake image data")
        captura["ruta_destino"] = str(archivo)
    metadatos_json.write_text(_json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return destino


@pytest.fixture()
def cliente_api(tmp_path):
    """Synchronous HTTP client using FastAPI/Starlette TestClient.
    Does not start a real server: tests are instant and port-free."""
    from fastapi.testclient import TestClient
    from photos_sync.web_server import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
