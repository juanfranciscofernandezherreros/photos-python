"""
conftest.py — shared fixtures for all tests.

Each test receives an isolated temporary directory. All config path
constants (METADATA_JSON, SSH_CONNECTIONS_JSON, etc.) are monkeypatched
to point into that tmp_path, so tests never touch ~/PhotosSync/data/.
"""
import json
import os
import time
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def cwd_temporal(tmp_path, monkeypatch):
    """Redirect all config path constants into tmp_path for full isolation.
    Without this, the absolute paths in config.py would write to the real
    ~/PhotosSync/data/ directory during tests."""
    monkeypatch.chdir(tmp_path)

    # Patch every path constant in config and every module that imported it —
    # including both the facade modules (photos_sync.folders, etc.) and the
    # actual implementation modules (photos_sync.storage.folders, etc.)
    import photos_sync.config as cfg
    import photos_sync.folders as folders_facade
    import photos_sync.connection as connection_facade
    import photos_sync.ssh_connection as ssh_facade
    import photos_sync.download as download_facade
    import photos_sync.compress as compress_facade
    import photos_sync.summary as summary_facade
    import photos_sync.organize as organize_facade
    import photos_sync.storage.folders as folders_impl
    import photos_sync.storage.connection as connection_impl
    import photos_sync.storage.ssh_repo as ssh_repo_impl
    import photos_sync.pipeline.download as download_impl
    import photos_sync.pipeline.compress as compress_impl
    import photos_sync.pipeline.summary as summary_impl
    import photos_sync.pipeline.organize as organize_impl
    import photos_sync.pipeline.upload_ssh as upload_impl

    all_modules = (
        cfg,
        folders_facade, connection_facade, ssh_facade,
        download_facade, compress_facade, summary_facade, organize_facade,
        folders_impl, connection_impl, ssh_repo_impl,
        download_impl, compress_impl, summary_impl, organize_impl, upload_impl,
    )

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    paths = {
        "METADATA_JSON":          str(tmp_path / "metadatos_screenshots.json"),
        "SELECTED_FOLDERS_JSON":  str(tmp_path / "carpetas_screenshots.json"),
        "DESTINATION_JSON":       str(tmp_path / "destino_guardado.json"),
        "DAILY_SUMMARY_JSON":     str(tmp_path / "resumen_por_dia.json"),
        "ORCHESTRATOR_LOG":       str(tmp_path / "orquestador.log"),
        "WEBDAV_CONNECTIONS_JSON":str(tmp_path / "conexiones_webdav.json"),
        "SSH_CONNECTIONS_JSON":   str(tmp_path / "conexiones_ssh.json"),
    }

    for attr, val in paths.items():
        for mod in all_modules:
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, val)

    # Also patch ORGANIZED_DIR so compress/organize use tmp_path
    org_dir = tmp_path / "organizado"
    for mod in all_modules:
        if hasattr(mod, "ORGANIZED_DIR"):
            monkeypatch.setattr(mod, "ORGANIZED_DIR", org_dir)

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
