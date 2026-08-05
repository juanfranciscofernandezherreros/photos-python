from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from photos_sync import config

config.ORCHESTRATOR_LOG = Path.cwd() / ".pytest_tmp_cli.log"
from photos_sync import cli  # noqa: E402
from photos_sync.pipeline import download, upload_ssh
from photos_sync.ssh import client as ssh_client


def _args(**overrides):
    values = dict(
        ssh_list=False,
        ssh_add=None,
        ssh_key="",
        ssh_rol="origen",
        ssh_remote_dest="",
        ssh_remove=None,
        ssh_test=None,
        todo=False,
        pasos=None,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def test_cli_step_execution_and_selection(monkeypatch):
    called = []
    assert cli.ejecutar_paso("ok", lambda: called.append("ok")) is True
    assert cli.ejecutar_paso("bad", lambda: (_ for _ in ()).throw(RuntimeError("boom"))) is False
    monkeypatch.setattr(cli, "prevent_sleep", lambda: SimpleNamespace(
        __enter__=lambda self: self, __exit__=lambda self, *args: None
    ))
    # A real context-manager class is clearer than teaching the production code about mocks.
    class Awake:
        def __enter__(self): return self
        def __exit__(self, *_): return None
    monkeypatch.setattr(cli, "prevent_sleep", Awake)
    assert cli.ejecutar_pasos([("one", lambda: called.append("one"))]) is True
    assert cli.ejecutar_pasos([("bad", lambda: (_ for _ in ()).throw(ValueError()))]) is False

    monkeypatch.setattr("photos_sync.db.get_engine", lambda: object())
    monkeypatch.setattr("photos_sync.db.init_db", lambda engine: called.append(engine))
    monkeypatch.setattr(cli, "ejecutar_pasos", lambda steps: len(steps) == 2)
    with pytest.raises(SystemExit, match="0"):
        cli.modo_cli(_args(pasos="1, 2, 99"))
    with pytest.raises(SystemExit, match="1"):
        cli.modo_cli(_args(pasos="bad"))
    with pytest.raises(SystemExit, match="1"):
        cli.modo_cli(_args(pasos="99"))


def test_cli_ssh_management_branches(monkeypatch, capsys):
    monkeypatch.setattr(cli.ssh_connection, "load_ssh_connections", lambda: [])
    assert cli.modo_gestion_ssh(_args(ssh_list=True)) is True
    assert "No SSH" in capsys.readouterr().out

    connection = {"alias": "nas", "usuario": "me", "host": "host", "puerto": 22,
                  "ruta_remota": "/in", "ruta_remota_destino": "/out", "rol": "ambos",
                  "clave_privada": "key"}
    monkeypatch.setattr(cli.ssh_connection, "load_ssh_connections", lambda: [connection])
    assert cli.modo_gestion_ssh(_args(ssh_list=True)) is True
    assert "nas" in capsys.readouterr().out

    saved = []
    monkeypatch.setattr(cli.ssh_connection, "add_or_update_ssh_connection", lambda **kw: saved.append(kw))
    assert cli.modo_gestion_ssh(_args(ssh_add=["nas", "host", "22", "me", "/in"])) is True
    assert saved[0]["puerto"] == 22
    with pytest.raises(SystemExit, match="1"):
        cli.modo_gestion_ssh(_args(ssh_add=["nas", "host", "nope", "me", "/in"]))

    removed = []
    monkeypatch.setattr(cli.ssh_connection, "remove_ssh_connection", removed.append)
    assert cli.modo_gestion_ssh(_args(ssh_remove="nas")) is True
    assert removed == ["nas"]
    monkeypatch.setattr(cli.ssh_connection, "get_connection", lambda alias: None)
    assert cli.modo_gestion_ssh(_args(ssh_test="missing")) is True
    monkeypatch.setattr(cli.ssh_connection, "get_connection", lambda alias: connection)
    monkeypatch.setattr(cli.ssh_connection, "paramiko_available", lambda: False)
    assert cli.modo_gestion_ssh(_args(ssh_test="nas")) is True
    assert cli.modo_gestion_ssh(_args()) is False


class FakeSftp:
    def __init__(self):
        self.paths = {"/root": SimpleNamespace(st_size=1), "/root/file.jpg": SimpleNamespace(st_size=12)}
        self.closed = False

    def close(self): self.closed = True
    def listdir(self, path): return ["ok"]
    def listdir_attr(self, path):
        if path == "/missing":
            raise FileNotFoundError
        if path == "/root":
            return [SimpleNamespace(filename="folder", st_mode=0o040755, st_size=0, st_mtime=1),
                    SimpleNamespace(filename="file.jpg", st_mode=0o100644, st_size=12, st_mtime=2),
                    SimpleNamespace(filename="skip.txt", st_mode=0o100644, st_size=2, st_mtime=2)]
        return [SimpleNamespace(filename="nested.png", st_mode=0o100644, st_size=5, st_mtime=3)]
    def get(self, remote, local): Path(local).write_bytes(b"photo")
    def put(self, local, remote): self.paths[remote] = SimpleNamespace(st_size=Path(local).stat().st_size)
    def stat(self, path):
        if path not in self.paths:
            raise FileNotFoundError
        return self.paths[path]
    def mkdir(self, path): self.paths[path] = SimpleNamespace(st_size=0)


class FakeParamikoClient:
    def __init__(self): self.sftp = FakeSftp(); self.kwargs = {}; self.closed = False
    def set_missing_host_key_policy(self, policy): pass
    def connect(self, **kwargs): self.kwargs = kwargs
    def open_sftp(self): return self.sftp
    def close(self): self.closed = True


def test_ssh_transport_without_network(monkeypatch, tmp_path):
    made = []
    fake_paramiko = SimpleNamespace(
        SSHClient=lambda: made.append(FakeParamikoClient()) or made[-1], AutoAddPolicy=lambda: object()
    )
    monkeypatch.setattr(ssh_client, "paramiko", fake_paramiko)
    conn = {"host": "example", "puerto": 2222, "usuario": "me", "ruta_remota": "/root",
            "clave_privada": "~/id_test"}
    with ssh_client.SSHClient(conn) as transport:
        assert made[-1].kwargs["port"] == 2222
        assert "key_filename" in made[-1].kwargs
        found = transport.list_files_recursive("/root", [".jpg", ".png"])
        assert {item["ruta"] for item in found} == {"/root/file.jpg", "/root/folder/nested.png"}
        assert transport.list_files_recursive("/missing", [".jpg"]) == []
        local = tmp_path / "downloads" / "one.jpg"
        transport.download("/root/file.jpg", local)
        assert local.read_bytes() == b"photo"
        transport.upload(local, "/new/path/one.jpg")
        assert transport.remote_exists("/new/path/one.jpg") == 5
        assert transport.remote_exists("/absent") is None
    assert made[-1].closed and made[-1].sftp.closed

    conn["clave_privada"] = ""
    password_client = ssh_client.SSHClient(conn, password="secret")
    password_client.connect()
    assert made[-1].kwargs["password"] == "secret"
    assert password_client.test_connection()[0] is True


def test_download_pipeline_local_and_ssh(monkeypatch, tmp_path):
    local = tmp_path / "Screenshot_20240102_030405.jpg"
    local.write_bytes(b"1234")
    ssh_conn = {"alias": "nas", "host": "host", "ruta_remota": "/photos", "usuario": "me"}

    class ScanClient:
        def __init__(self, conn): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def list_files_recursive(self, *_):
            return [{"ruta": "/photos/Screenshot_20240203.png", "tamano": 1024, "mtime": 1.0}]

    monkeypatch.setattr(download, "load_saved_folders", lambda: [tmp_path])
    monkeypatch.setattr(download.ssh_connection, "connections_by_role", lambda role: [ssh_conn])
    monkeypatch.setattr(download.ssh_connection, "paramiko_available", lambda: True)
    monkeypatch.setattr(download.ssh_connection, "SSHClient", ScanClient)
    monkeypatch.setattr(download.connection, "load_connections", lambda: [])
    monkeypatch.setattr(download, "progress_bar", lambda items, **kwargs: items)
    monkeypatch.setattr(download, "load_existing_metadata", lambda: {})
    stored = []
    monkeypatch.setattr(download.repo, "upsert_captures", lambda rows: stored.extend(rows))
    download.sync_captures()
    assert len(stored) == 2
    assert {row["fecha_captura"][:10] for row in stored} == {"2024-01-02", "2024-02-03"}
    assert download.get_actual_date("plain.jpg", 0).startswith("1970-01-01")


def test_upload_pipeline_and_retry(monkeypatch, tmp_path):
    photo = tmp_path / "2024" / "one.jpg"
    photo.parent.mkdir(); photo.write_bytes(b"photo")
    conn = {"alias": "nas", "host": "host", "usuario": "me", "ruta_remota": "/in",
            "ruta_remota_destino": "/out", "rol": "destino"}

    class UploadClient:
        uploads = []
        def __init__(self, connection): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def remote_exists(self, path): return None
        def upload(self, local, remote): self.uploads.append((local, remote))

    monkeypatch.setattr(upload_ssh.ssh_connection, "SSHClient", UploadClient)
    monkeypatch.setattr(upload_ssh.ssh_connection, "effective_destination_path", lambda c: "/out")
    monkeypatch.setattr(upload_ssh, "track", lambda items, **kwargs: items)
    assert upload_ssh._upload_with_retry(conn, [photo], tmp_path) == (1, 0, 0)
    assert UploadClient.uploads[0][1] == "/out/2024/one.jpg"

    monkeypatch.setattr(upload_ssh.ssh_connection, "paramiko_available", lambda: True)
    monkeypatch.setattr(upload_ssh, "_destination_servers", lambda: [conn])
    monkeypatch.setattr(upload_ssh, "_local_organized_folder", lambda: tmp_path)
    upload_ssh.upload_organized_to_ssh()

    monkeypatch.setattr(upload_ssh.ssh_connection, "paramiko_available", lambda: False)
    upload_ssh.upload_organized_to_ssh()
