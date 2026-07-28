"""
Tests for the web API (photos_sync.web_server)
───────────────────────────────────────────────
Uses httpx with ASGITransport: no real server, tests are instant.
Covers all endpoints: steps, pipeline, SSH, WebDAV, source and
destination folders.
"""
import json
import pytest
from photos_sync import ssh_connection
from photos_sync.folders import save_destination


# ═══════════════════════════════════════ /api/pasos ══════════════════════════

class TestPasos:
    def test_devuelve_5_pasos(self, cliente_api):
        r = cliente_api.get("/api/pasos")
        assert r.status_code == 200
        pasos = r.json()
        assert len(pasos) == 5

    def test_estructura_paso(self, cliente_api):
        pasos = cliente_api.get("/api/pasos").json()
        for p in pasos:
            assert "id" in p and "nombre" in p
            assert isinstance(p["id"], int)

    def test_ids_secuenciales(self, cliente_api):
        ids = [p["id"] for p in cliente_api.get("/api/pasos").json()]
        assert ids == list(range(5))


# ═══════════════════════════════════════ /api/pipeline ═══════════════════════

class TestPipeline:
    def test_estado_inicial_no_corriendo(self, cliente_api):
        r = cliente_api.get("/api/pipeline/estado")
        assert r.status_code == 200
        assert r.json()["corriendo"] is False

    def test_ejecutar_pasos_validos(self, cliente_api):
        r = cliente_api.post("/api/pipeline/ejecutar", json={"pasos": [0]})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_ejecutar_todos_pasos_null(self, cliente_api):
        r = cliente_api.post("/api/pipeline/ejecutar", json={"pasos": None})
        assert r.status_code == 200

    def test_indice_fuera_de_rango_ignorado(self, cliente_api):
        r = cliente_api.post("/api/pipeline/ejecutar", json={"pasos": [99]})
        assert r.status_code == 200
        assert r.json()["pasos"] == []


# ═══════════════════════════════════════ /api/ssh ════════════════════════════

class TestSSHApi:
    def test_lista_vacia_inicial(self, cliente_api):
        r = cliente_api.get("/api/ssh")
        assert r.status_code == 200
        assert r.json() == []

    def test_guardar_conexion(self, cliente_api):
        r = cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.2.3.4", "puerto": 22,
            "usuario": "juan", "ruta_remota": "/fotos", "rol": "origen",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_listar_tras_guardar(self, cliente_api):
        cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.2.3.4", "puerto": 22,
            "usuario": "juan", "ruta_remota": "/fotos", "rol": "origen",
        })
        lista = cliente_api.get("/api/ssh").json()
        assert len(lista) == 1
        assert lista[0]["alias"] == "nas1"

    def test_ambos_sin_ruta_destino_400(self, cliente_api):
        r = cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.2.3.4", "puerto": 22,
            "usuario": "juan", "ruta_remota": "/fotos",
            "rol": "ambos", "ruta_remota_destino": "",
        })
        assert r.status_code == 400
        assert "ruta" in r.json()["detail"].lower()

    def test_ambos_misma_ruta_400(self, cliente_api):
        r = cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.2.3.4", "puerto": 22,
            "usuario": "juan", "ruta_remota": "/fotos",
            "rol": "ambos", "ruta_remota_destino": "/fotos",
        })
        assert r.status_code == 400

    def test_ambos_rutas_distintas_ok(self, cliente_api):
        r = cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.2.3.4", "puerto": 22,
            "usuario": "juan", "ruta_remota": "/fotos",
            "rol": "ambos", "ruta_remota_destino": "/backup",
        })
        assert r.status_code == 200

    def test_eliminar_conexion(self, cliente_api):
        cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.2.3.4", "puerto": 22,
            "usuario": "juan", "ruta_remota": "/fotos", "rol": "origen",
        })
        r = cliente_api.delete("/api/ssh/nas1")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert cliente_api.get("/api/ssh").json() == []

    def test_roles_devuelve_estructura_completa(self, cliente_api):
        r = cliente_api.get("/api/ssh/roles")
        assert r.status_code == 200
        data = r.json()
        assert set(data["roles"]) == {"origen", "destino", "ambos"}
        assert "ambos" in data["ruta_destino_obligatoria"]
        assert "descripcion" in data
        for rol in data["roles"]:
            assert rol in data["descripcion"]

    def test_roles_requiere_ruta_destino_incluye_destino_y_ambos(self, cliente_api):
        data = cliente_api.get("/api/ssh/roles").json()
        assert set(data["requiere_ruta_destino"]) == {"destino", "ambos"}


# ═══════════════════════════════════════ /api/webdav ═════════════════════════

class TestWebDAVApi:
    def test_lista_vacia_inicial(self, cliente_api):
        r = cliente_api.get("/api/webdav")
        assert r.status_code == 200
        assert r.json() == []

    def test_letras_devuelve_rango_correcto(self, cliente_api):
        r = cliente_api.get("/api/webdav/letras")
        assert r.status_code == 200
        data = r.json()
        assert "D:" in data["todas"]
        assert "Z:" in data["todas"]
        assert "A:" not in data["todas"]
        assert "C:" not in data["todas"]
        assert len(data["todas"]) == 23

    def test_letras_libres_excluye_usadas(self, cliente_api):
        from photos_sync import connection as _c
        _c.add_or_update_connection("Z:", "1.1.1.1", "8080", "test")
        data = cliente_api.get("/api/webdav/letras").json()
        assert "Z:" not in data["libres"]
        assert "Z:" in data["todas"]

    def test_connect_en_linux_devuelve_ok_false_con_mensaje(self, cliente_api):
        r = cliente_api.post("/api/webdav/connect", json={
            "letra": "Z:", "ip": "192.168.1.1", "puerto": "8080", "alias": "test",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "Windows" in data["mensaje"]

    def test_desconnect_en_linux_devuelve_ok_false(self, cliente_api):
        r = cliente_api.post("/api/webdav/desconnect/Z%3A")
        assert r.status_code == 200
        assert r.json()["ok"] is False


# ═══════════════════════════════════════ /api/carpetas ═══════════════════════

class TestCarpetasApi:
    def test_get_carpetas_estructura(self, cliente_api):
        r = cliente_api.get("/api/carpetas")
        assert r.status_code == 200
        data = r.json()
        assert "origen" in data
        assert "destino" in data
        assert "servidores_ssh_destino" in data

    def test_anadir_carpeta_origen(self, cliente_api):
        r = cliente_api.post("/api/carpetas/origen/anadir",
                             json={"carpeta": "/mnt/fotos"})
        assert r.status_code == 200
        assert "/mnt/fotos" in r.json()["origen"]

    def test_anadir_carpeta_vacia_400(self, cliente_api):
        r = cliente_api.post("/api/carpetas/origen/anadir", json={"carpeta": ""})
        assert r.status_code == 400

    def test_anadir_carpeta_no_duplica(self, cliente_api):
        cliente_api.post("/api/carpetas/origen/anadir", json={"carpeta": "/mnt/fotos"})
        cliente_api.post("/api/carpetas/origen/anadir", json={"carpeta": "/mnt/fotos"})
        origen = cliente_api.get("/api/carpetas").json()["origen"]
        assert origen.count("/mnt/fotos") == 1

    def test_remove_carpeta_origen(self, cliente_api):
        cliente_api.post("/api/carpetas/origen/anadir", json={"carpeta": "/mnt/fotos"})
        r = cliente_api.post("/api/carpetas/origen/quitar", json={"carpeta": "/mnt/fotos"})
        assert r.status_code == 200
        assert "/mnt/fotos" not in r.json()["origen"]

    def test_save_destination_local(self, cliente_api):
        r = cliente_api.post("/api/carpetas/destino",
                             json={"tipo": "local", "ruta": "/tmp/salida"})
        assert r.status_code == 200
        assert r.json()["destino"]["tipo"] == "local"

    def test_save_destination_local_sin_ruta_400(self, cliente_api):
        r = cliente_api.post("/api/carpetas/destino", json={"tipo": "local", "ruta": ""})
        assert r.status_code == 400

    def test_save_ssh_destination_rol_origen_400(self, cliente_api):
        cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.1.1.1", "puerto": 22,
            "usuario": "u", "ruta_remota": "/r", "rol": "origen",
        })
        r = cliente_api.post("/api/carpetas/destino",
                             json={"tipo": "ssh", "alias": "nas1"})
        assert r.status_code == 400
        assert "rol" in r.json()["detail"].lower()

    def test_save_ssh_destination_inexistente_404(self, cliente_api):
        r = cliente_api.post("/api/carpetas/destino",
                             json={"tipo": "ssh", "alias": "no-existe"})
        assert r.status_code == 404

    def test_save_ssh_destination_rol_destino_ok(self, cliente_api):
        cliente_api.post("/api/ssh", json={
            "alias": "nas2", "host": "2.2.2.2", "puerto": 22,
            "usuario": "u", "ruta_remota": "/bk", "rol": "destino",
        })
        r = cliente_api.post("/api/carpetas/destino",
                             json={"tipo": "ssh", "alias": "nas2"})
        assert r.status_code == 200
        assert r.json()["destino"]["alias"] == "nas2"

    def test_save_ssh_destination_rol_ambos_ok(self, cliente_api):
        cliente_api.post("/api/ssh", json={
            "alias": "nas3", "host": "3.3.3.3", "puerto": 22,
            "usuario": "u", "ruta_remota": "/src",
            "ruta_remota_destino": "/dst", "rol": "ambos",
        })
        r = cliente_api.post("/api/carpetas/destino",
                             json={"tipo": "ssh", "alias": "nas3"})
        assert r.status_code == 200

    def test_tipo_invalido_400(self, cliente_api):
        r = cliente_api.post("/api/carpetas/destino",
                             json={"tipo": "ftp", "ruta": "/x"})
        assert r.status_code == 400

    def test_servidores_ssh_destino_filtra_solo_destino_y_ambos(self, cliente_api):
        # nas-o: source only → must NOT appear
        cliente_api.post("/api/ssh", json={
            "alias": "nas-o", "host": "1.1.1.1", "puerto": 22,
            "usuario": "u", "ruta_remota": "/r", "rol": "origen",
        })
        # nas-d: destination → YES
        cliente_api.post("/api/ssh", json={
            "alias": "nas-d", "host": "2.2.2.2", "puerto": 22,
            "usuario": "u", "ruta_remota": "/r", "rol": "destino",
        })
        # nas-a: both → YES
        cliente_api.post("/api/ssh", json={
            "alias": "nas-a", "host": "3.3.3.3", "puerto": 22,
            "usuario": "u", "ruta_remota": "/src",
            "ruta_remota_destino": "/dst", "rol": "ambos",
        })
        servidores = cliente_api.get("/api/carpetas").json()["servidores_ssh_destino"]
        aliases = [s["alias"] for s in servidores]
        assert "nas-o" not in aliases
        assert "nas-d" in aliases
        assert "nas-a" in aliases


# ═══════════════════════════════════════ / (HTML) ════════════════════════════

class TestUIHtml:
    def test_devuelve_html(self, cliente_api):
        r = cliente_api.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_html_contiene_secciones_principales(self, cliente_api):
        html = cliente_api.get("/").text
        for seccion in ["pipeline", "ssh", "webdav", "carpetas"]:
            assert seccion in html.lower(), f"Missing section '{seccion}' in the HTML"

    def test_html_contiene_websocket(self, cliente_api):
        assert "ws/log" in cliente_api.get("/").text

    def test_html_endpoints_coinciden_con_api(self, cliente_api):
        """Los endpoints llamados desde el JS deben existir en la API."""
        html = cliente_api.get("/").text
        endpoints_esperados = [
            "/api/pasos", "/api/pipeline/ejecutar", "/api/pipeline/estado",
            "/api/ssh", "/api/ssh/roles", "/api/webdav", "/api/webdav/letras",
            "/api/webdav/connect", "/api/carpetas", "/api/carpetas/origen/anadir",
            "/api/carpetas/origen/quitar", "/api/carpetas/destino",
        ]
        for ep in endpoints_esperados:
            assert ep in html, f"El endpoint '{ep}' no aparece en el HTML/JS"
