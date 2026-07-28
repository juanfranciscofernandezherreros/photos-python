"""
Tests de photos_sync.ssh_conexion
──────────────────────────────────
Cubre: guardar, actualizar, eliminar, obtener, connections_by_role,
effective_destination_path, y todas las validaciones del rol "ambos".
"""
import pytest
from photos_sync import ssh_connection


# ─────────────────────────────── helpers ────────────────────────────────────

def _guardar(**kwargs):
    defaults = dict(alias="nas1", host="1.2.3.4", puerto=22,
                    usuario="juan", ruta_remota="/fotos", rol="origen")
    defaults.update(kwargs)
    return ssh_conexion.add_or_update_ssh_connection(**defaults)


# ──────────────────────────────── CRUD básico ────────────────────────────────

class TestCRUD:
    def test_guardar_y_obtener(self):
        _guardar()
        c = ssh_connection.get_connection("nas1")
        assert c is not None
        assert c["host"] == "1.2.3.4"
        assert c["rol"] == "origen"

    def test_lista_vacia_inicial(self):
        assert ssh_connection.load_ssh_connections() == []

    def test_actualizar_sobreescribe(self):
        _guardar()
        _guardar(host="9.9.9.9")
        lista = ssh_connection.load_ssh_connections()
        assert len(lista) == 1
        assert lista[0]["host"] == "9.9.9.9"

    def test_varias_conexiones(self):
        _guardar(alias="nas1")
        _guardar(alias="nas2", host="2.2.2.2")
        lista = ssh_connection.load_ssh_connections()
        assert len(lista) == 2

    def test_eliminar(self):
        _guardar(alias="nas1")
        _guardar(alias="nas2", host="2.2.2.2")
        ssh_connection.remove_ssh_connection("nas1")
        assert ssh_connection.get_connection("nas1") is None
        assert ssh_connection.get_connection("nas2") is not None

    def test_obtener_inexistente_devuelve_none(self):
        assert ssh_connection.get_connection("no-existe") is None

    def test_puerto_por_defecto(self):
        _guardar(puerto=0)
        c = ssh_connection.get_connection("nas1")
        assert c["puerto"] == ssh_connection.DEFAULT_SSH_PORT

    def test_rol_invalido_cae_a_origen(self):
        _guardar(rol="inventado")
        c = ssh_connection.get_connection("nas1")
        assert c["rol"] == "origen"


# ─────────────────────────────── roles ──────────────────────────────────────

class TestRoles:
    def test_connections_by_role_origen(self):
        _guardar(alias="nas-o", rol="origen")
        _guardar(alias="nas-d", host="2.2.2.2", rol="destino")
        resultado = ssh_connection.connections_by_role("origen")
        aliases = [c["alias"] for c in resultado]
        assert "nas-o" in aliases
        assert "nas-d" not in aliases

    def test_connections_by_role_destino(self):
        _guardar(alias="nas-o", rol="origen")
        _guardar(alias="nas-d", host="2.2.2.2", rol="destino")
        resultado = ssh_connection.connections_by_role("destino")
        aliases = [c["alias"] for c in resultado]
        assert "nas-d" in aliases
        assert "nas-o" not in aliases

    def test_ambos_aparece_en_origen_y_destino(self):
        _guardar(alias="nas-a", rol="ambos",
                 ruta_remota="/src", ruta_remota_destino="/dst")
        assert any(c["alias"] == "nas-a" for c in ssh_connection.connections_by_role("origen"))
        assert any(c["alias"] == "nas-a" for c in ssh_connection.connections_by_role("destino"))


# ─────────────────── validaciones rol "ambos" ───────────────────────────────

class TestValidacionAmbos:
    def test_ambos_sin_ruta_destino_lanza_valueerror(self):
        with pytest.raises(ValueError, match="ruta remota de destino"):
            _guardar(rol="ambos", ruta_remota="/fotos", ruta_remota_destino="")

    def test_ambos_con_misma_ruta_lanza_valueerror(self):
        with pytest.raises(ValueError, match="igual a la de origen"):
            _guardar(rol="ambos", ruta_remota="/fotos", ruta_remota_destino="/fotos")

    def test_ambos_con_trailing_slash_detecta_igualdad(self):
        with pytest.raises(ValueError):
            _guardar(rol="ambos", ruta_remota="/fotos/", ruta_remota_destino="/fotos")

    def test_ambos_correcto_se_guarda(self):
        _guardar(rol="ambos", ruta_remota="/fotos", ruta_remota_destino="/backup")
        c = ssh_connection.get_connection("nas1")
        assert c["rol"] == "ambos"
        assert c["ruta_remota_destino"] == "/backup"

    def test_origen_no_requiere_ruta_destino(self):
        _guardar(rol="origen", ruta_remota_destino="")  # no debe lanzar
        c = ssh_connection.get_connection("nas1")
        assert c["rol"] == "origen"

    def test_destino_no_requiere_ruta_destino(self):
        _guardar(rol="destino", ruta_remota_destino="")  # no debe lanzar
        c = ssh_connection.get_connection("nas1")
        assert c["rol"] == "destino"


# ──────────────────────── effective_destination_path ─────────────────────────────

class TestRutaDestinoEfectiva:
    def test_usa_ruta_destino_si_existe(self):
        _guardar(rol="ambos", ruta_remota="/src", ruta_remota_destino="/dst")
        c = ssh_connection.get_connection("nas1")
        assert ssh_connection.effective_destination_path(c) == "/dst"

    def test_fallback_a_ruta_remota_si_no_hay_destino(self):
        _guardar(rol="destino", ruta_remota="/backup", ruta_remota_destino="")
        c = ssh_connection.get_connection("nas1")
        assert ssh_connection.effective_destination_path(c) == "/backup"

    def test_compatibilidad_conexion_sin_campo_destino(self):
        """Connectiones guardadas antes de añadir ruta_remota_destino no tienen
        ese campo; effective_destination_path no debe fallar."""
        c = {"alias": "viejo", "host": "x", "puerto": 22, "usuario": "u",
             "ruta_remota": "/old", "clave_privada": "", "rol": "destino"}
        assert ssh_connection.effective_destination_path(c) == "/old"
