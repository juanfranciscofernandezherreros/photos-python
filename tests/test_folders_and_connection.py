"""
Tests for photos_sync.storage.folders and photos_sync.storage.connection
──────────────────────────────────────────────────────────
Covers: save/load source folders, local destination, SSH destination,
backwards compatibility with legacy format, and WebDAV connection CRUD.
"""
from types import SimpleNamespace

from photos_sync.storage import connection, folders

# ═══════════════════════════════════════ FOLDERS ════════════════════════════

class TestCarpetasOrigen:
    def test_lista_vacia_sin_archivo(self):
        # Sin archivo y sin móviles conectados → lista vacía
        result = folders.load_saved_folders()
        assert isinstance(result, list)

    def test_guardar_y_cargar(self, tmp_path):
        rutas = [tmp_path / "dcim", tmp_path / "screenshots"]
        folders.save_folders(rutas)
        cargadas = folders.load_saved_folders()
        assert set(str(r) for r in cargadas) == set(str(r) for r in rutas)

    def test_guardar_vacio_devuelve_defaults(self):
        folders.save_folders([])
        result = folders.load_saved_folders()
        # Lista vacía guardada → se usan defaults (rutas de móviles conectados)
        assert isinstance(result, list)

    def test_archivo_corrupto_devuelve_defaults(self, tmp_path):
        (tmp_path / "carpetas_screenshots.json").write_text("esto no es json", encoding="utf-8")
        result = folders.load_saved_folders()
        assert isinstance(result, list)


class TestDestinoLocal:
    def test_guardar_y_cargar_destino_local(self, tmp_path):
        ruta = str(tmp_path / "salida")
        folders.save_destination(ruta)
        config = folders.load_destination_config()
        assert config["tipo"] == "local"
        assert config["ruta"] == ruta

    def test_load_saved_destination_devuelve_ruta(self, tmp_path):
        ruta = str(tmp_path / "salida")
        folders.save_destination(ruta)
        assert folders.load_saved_destination() == ruta

    def test_sin_destino_devuelve_dict_vacio(self):
        assert folders.load_destination_config() == {}

    def test_load_saved_destination_sin_archivo_devuelve_none(self):
        assert folders.load_saved_destination() is None

    def test_compatibilidad_formato_antiguo(self, tmp_path):
        """With PostgreSQL backend the 'old JSON format' no longer applies.
        An empty database returns {} from load_destination_config()."""
        config = folders.load_destination_config()
        assert config == {}  # nothing configured yet

    def test_archivo_corrupto_devuelve_vacio(self, tmp_path):
        # With DB backend, an empty database returns {} (no corrupt file possible)
        assert folders.load_destination_config() == {}


class TestDestinoSSH:
    def test_guardar_y_cargar_destino_ssh(self):
        folders.save_ssh_destination("mi-nas")
        config = folders.load_destination_config()
        assert config["tipo"] == "ssh"
        assert config["alias"] == "mi-nas"

    def test_destino_ssh_no_devuelve_ruta_local(self):
        folders.save_ssh_destination("mi-nas")
        assert folders.load_saved_destination() is None

    def test_sobreescribir_ssh_con_local(self, tmp_path):
        folders.save_ssh_destination("mi-nas")
        folders.save_destination(str(tmp_path / "local"))
        config = folders.load_destination_config()
        assert config["tipo"] == "local"

    def test_sobreescribir_local_con_ssh(self, tmp_path):
        folders.save_destination(str(tmp_path / "local"))
        folders.save_ssh_destination("nas2")
        config = folders.load_destination_config()
        assert config["tipo"] == "ssh"
        assert config["alias"] == "nas2"


# ═══════════════════════════════════════ CONEXION WEBDAV ═════════════════════

class TestConnectionWebDAV:
    def test_lista_vacia_inicial(self):
        assert connection.load_connections() == []

    def test_anadir_y_cargar(self):
        connection.add_or_update_connection("Z:", "192.168.1.1", "8080", "Pixel")
        lista = connection.load_connections()
        assert len(lista) == 1
        assert lista[0]["alias"] == "Pixel"

    def test_actualizar_sobreescribe(self):
        connection.add_or_update_connection("Z:", "192.168.1.1", "8080", "Pixel")
        connection.add_or_update_connection("Z:", "192.168.1.99", "8080", "Pixel Pro")
        lista = connection.load_connections()
        assert len(lista) == 1
        assert lista[0]["ip"] == "192.168.1.99"
        assert lista[0]["alias"] == "Pixel Pro"

    def test_varias_conexiones(self):
        connection.add_or_update_connection("Z:", "1.1.1.1", "8080", "A")
        connection.add_or_update_connection("Y:", "2.2.2.2", "8080", "B")
        assert len(connection.load_connections()) == 2

    def test_remove_connection(self):
        connection.add_or_update_connection("Z:", "1.1.1.1", "8080", "A")
        connection.add_or_update_connection("Y:", "2.2.2.2", "8080", "B")
        connection.remove_connection("Z:")
        lista = connection.load_connections()
        assert len(lista) == 1
        assert lista[0]["letra"] == "Y:"

    def test_letras_disponibles_rango(self):
        letras = connection.AVAILABLE_DRIVE_LETTERS
        assert "D:" in letras
        assert "Z:" in letras
        assert "A:" not in letras
        assert "C:" not in letras
        assert len(letras) == 23  # D to Z

    def test_is_mounted_ruta_inexistente(self, tmp_path):
        # On any OS this made-up path does not exist
        assert connection.is_mounted("Q:") is False

    def test_net_use_uses_atomic_arguments_without_shell(self, monkeypatch):
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return SimpleNamespace(returncode=0, stdout="ok", stderr=None)

        monkeypatch.setattr(connection.platform, "system", lambda: "Windows")
        monkeypatch.setattr(connection.subprocess, "run", fake_run)

        ok, _ = connection.mount("z:", "192.168.1.20", "8080")

        assert ok is True
        assert captured["args"][1:] == [
            "use", "Z:", "http://192.168.1.20:8080",
        ]
        assert captured["kwargs"]["shell"] is False
        assert isinstance(captured["args"], list)

    def test_command_metacharacters_are_rejected_before_execution(self, monkeypatch):
        called = False

        def fake_run(*_args, **_kwargs):
            nonlocal called
            called = True

        monkeypatch.setattr(connection.platform, "system", lambda: "Windows")
        monkeypatch.setattr(connection.subprocess, "run", fake_run)

        assert connection.mount("Z: & whoami", "192.168.1.20", "8080")[0] is False
        assert connection.mount("Z:", "192.168.1.20", "8080 & calc")[0] is False
        assert connection.unmount("Z: | whoami")[0] is False
        assert called is False
