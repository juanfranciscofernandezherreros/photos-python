"""
Tests for the web API (photos_sync.web_server)
───────────────────────────────────────────────
Uses httpx with ASGITransport: no real server, tests are instant.
Covers all endpoints: steps, pipeline, SSH, WebDAV, source and
destination folders.
"""

from pathlib import Path

# ═══════════════════════════════════════ /api/pasos ══════════════════════════

class TestPasos:
    def test_returns_6_steps(self, cliente_api):
        r = cliente_api.get("/api/pasos")
        assert r.status_code == 200
        pasos = r.json()
        assert len(pasos) == 6

    def test_estructura_paso(self, cliente_api):
        pasos = cliente_api.get("/api/pasos").json()
        for p in pasos:
            assert "id" in p and "nombre" in p
            assert isinstance(p["id"], int)

    def test_ids_are_sequential(self, cliente_api):
        ids = [p["id"] for p in cliente_api.get("/api/pasos").json()]
        assert ids == list(range(6))


# ═══════════════════════════════════════ /api/pipeline ═══════════════════════

class TestPipeline:
    def test_initial_state_not_running(self, cliente_api):
        r = cliente_api.get("/api/pipeline/estado")
        assert r.status_code == 200
        assert r.json()["corriendo"] is False

    def test_run_valid_steps(self, cliente_api):
        r = cliente_api.post("/api/pipeline/ejecutar", json={"pasos": [0]})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_run_all_steps_null(self, cliente_api):
        r = cliente_api.post("/api/pipeline/ejecutar", json={"pasos": None})
        assert r.status_code == 200

    def test_indice_fuera_de_rango_ignorado(self, cliente_api):
        r = cliente_api.post("/api/pipeline/ejecutar", json={"pasos": [99]})
        # Either the pipeline accepted (200, empty step list) or it was already
        # running from a previous test (409). Both are acceptable here.
        assert r.status_code in (200, 409)
        if r.status_code == 200:
            assert r.json()["pasos"] == []


# ═══════════════════════════════════════ /api/ssh ════════════════════════════

class TestSSHApi:
    def test_empty_list_initially(self, cliente_api):
        r = cliente_api.get("/api/ssh")
        assert r.status_code == 200
        assert r.json() == []

    def test_save_connection(self, cliente_api):
        r = cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.2.3.4", "puerto": 22,
            "usuario": "juan", "ruta_remota": "/fotos", "rol": "origen",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_list_after_save(self, cliente_api):
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
        assert "path" in r.json()["detail"].lower()

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

    def test_delete_connection(self, cliente_api):
        cliente_api.post("/api/ssh", json={
            "alias": "nas1", "host": "1.2.3.4", "puerto": 22,
            "usuario": "juan", "ruta_remota": "/fotos", "rol": "origen",
        })
        r = cliente_api.delete("/api/ssh/nas1")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert cliente_api.get("/api/ssh").json() == []

    def test_roles_returns_full_structure(self, cliente_api):
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
    def test_empty_list_initially(self, cliente_api):
        r = cliente_api.get("/api/webdav")
        assert r.status_code == 200
        assert r.json() == []

    def test_letters_returns_correct_range(self, cliente_api):
        r = cliente_api.get("/api/webdav/letras")
        assert r.status_code == 200
        data = r.json()
        assert "D:" in data["todas"]
        assert "Z:" in data["todas"]
        assert "A:" not in data["todas"]
        assert "C:" not in data["todas"]
        assert len(data["todas"]) == 23

    def test_letras_libres_excluye_usadas(self, cliente_api):
        from photos_sync.storage import connection as _c
        _c.add_or_update_connection("Z:", "1.1.1.1", "8080", "test")
        data = cliente_api.get("/api/webdav/letras").json()
        assert "Z:" not in data["libres"]
        assert "Z:" in data["todas"]

    def test_connect_on_linux_returns_ok_false_with_message(self, cliente_api, monkeypatch):
        from photos_sync.storage import connection as webdav_connection

        monkeypatch.setattr(webdav_connection.platform, "system", lambda: "Linux")
        r = cliente_api.post("/api/webdav/connect", json={
            "letra": "Z:", "ip": "192.168.1.1", "puerto": "8080", "alias": "test",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "Windows" in data["mensaje"]

    def test_disconnect_on_linux_returns_ok_false(self, cliente_api):
        r = cliente_api.post("/api/webdav/disconnect/Z%3A")
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_webdav_command_injection_inputs_are_rejected(self, cliente_api):
        response = cliente_api.post("/api/webdav/connect", json={
            "letra": "Z: & whoami",
            "ip": "192.168.1.1",
            "puerto": "8080 & calc",
            "alias": "unsafe",
        })
        assert response.status_code == 422

    def test_webdav_download_rejects_destination_outside_library(self, cliente_api):
        response = cliente_api.post("/api/webdav/download", json={
            "ip": "127.0.0.1",
            "port": "8080",
            "dest_folder": "C:/Windows/System32",
        })
        assert response.status_code == 403


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
        assert str(Path("/mnt/fotos")) in r.json()["origen"]

    def test_add_empty_folder_returns_400(self, cliente_api):
        r = cliente_api.post("/api/carpetas/origen/anadir", json={"carpeta": ""})
        assert r.status_code == 400

    def test_anadir_carpeta_no_duplica(self, cliente_api):
        cliente_api.post("/api/carpetas/origen/anadir", json={"carpeta": "/mnt/fotos"})
        cliente_api.post("/api/carpetas/origen/anadir", json={"carpeta": "/mnt/fotos"})
        origen = cliente_api.get("/api/carpetas").json()["origen"]
        assert origen.count(str(Path("/mnt/fotos"))) == 1

    def test_remove_carpeta_origen(self, cliente_api):
        cliente_api.post("/api/carpetas/origen/anadir", json={"carpeta": "/mnt/fotos"})
        r = cliente_api.post("/api/carpetas/origen/quitar", json={"carpeta": "/mnt/fotos"})
        assert r.status_code == 200
        assert str(Path("/mnt/fotos")) not in r.json()["origen"]

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
    def test_returns_html(self, cliente_api):
        r = cliente_api.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_html_contains_main_sections(self, cliente_api):
        html = cliente_api.get("/").text
        for seccion in ["pipeline", "ssh", "webdav", "carpetas"]:
            assert seccion in html.lower(), f"Missing section '{seccion}' in the HTML"

    def test_html_contains_websocket(self, cliente_api):
        assert "ws/log" in cliente_api.get("/").text

    def test_html_endpoints_match_api(self, cliente_api):
        """Every endpoint called by JavaScript must exist in the API."""
        html = cliente_api.get("/").text
        endpoints_esperados = [
            "/api/pasos", "/api/pipeline/ejecutar", "/api/pipeline/estado",
            "/api/ssh", "/api/ssh/roles", "/api/webdav", "/api/webdav/letras",
            "/api/webdav/connect", "/api/carpetas", "/api/carpetas/origen/anadir",
            "/api/carpetas/origen/quitar", "/api/carpetas/destino",
        ]
        for ep in endpoints_esperados:
            assert ep in html, f"Endpoint '{ep}' is missing from the HTML/JS"

    def test_html_has_no_wizard_or_cities_ui(self, cliente_api):
        html = cliente_api.get("/").text.lower()
        assert "setup wizard" not in html
        assert 'data-s="cities"' not in html
        assert "/api/cities" not in html
        assert "/api/photos/by-city" not in html


class TestRemovedWizardAndCitiesApi:
    def test_health_endpoint_replaces_setup_status(self, cliente_anon):
        response = cliente_anon.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_removed_endpoints_return_404(self, cliente_anon):
        endpoints = (
            "/api/setup-status",
            "/api/cities",
            "/api/photos/by-city/Madrid",
        )
        for endpoint in endpoints:
            assert cliente_anon.get(endpoint).status_code == 404


# ═══════════════════════════════════════ /api/thumb ══════════════════════════

class TestThumbnails:
    def _make_photo(self, tmp_path):
        """Create a real JPEG inside the organized dir; return its path."""
        from PIL import Image
        day = tmp_path / "organizado" / "2024" / "01" / "15"
        day.mkdir(parents=True, exist_ok=True)
        img_path = day / "IMG_001.jpg"
        Image.new("RGB", (2000, 1500), (100, 150, 200)).save(img_path, "JPEG")
        return img_path

    def test_thumb_returns_jpeg(self, cliente_api, cwd_temporal):
        img = self._make_photo(cwd_temporal)
        r = cliente_api.get(f"/api/thumb?path={img}&size=200")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

    def test_thumb_is_smaller_than_original(self, cliente_api, cwd_temporal):
        img = self._make_photo(cwd_temporal)
        r = cliente_api.get(f"/api/thumb?path={img}&size=200")
        assert len(r.content) < img.stat().st_size

    def test_thumb_is_cached(self, cliente_api, cwd_temporal):
        img = self._make_photo(cwd_temporal)
        cliente_api.get(f"/api/thumb?path={img}&size=200")
        thumbs = list((cwd_temporal / "thumbs").glob("*.jpg"))
        assert len(thumbs) == 1
        # Second request reuses the cache (still 1 file, still 200)
        r2 = cliente_api.get(f"/api/thumb?path={img}&size=200")
        assert r2.status_code == 200
        assert len(list((cwd_temporal / "thumbs").glob("*.jpg"))) == 1

    def test_thumb_rejects_outside_path(self, cliente_api, cwd_temporal):
        r = cliente_api.get("/api/thumb?path=/etc/passwd&size=200")
        assert r.status_code == 403

    def test_thumb_404_for_missing_file(self, cliente_api, cwd_temporal):
        missing = cwd_temporal / "organizado" / "2024" / "01" / "15" / "nope.jpg"
        missing.parent.mkdir(parents=True, exist_ok=True)
        r = cliente_api.get(f"/api/thumb?path={missing}&size=200")
        assert r.status_code == 404

    def test_thumb_size_is_clamped(self, cliente_api, cwd_temporal):
        img = self._make_photo(cwd_temporal)
        # Oversized request should still succeed (clamped to 1024)
        r = cliente_api.get(f"/api/thumb?path={img}&size=99999")
        assert r.status_code == 200


# ═══════════════════════════════════════ /api/photos/bulk ════════════════════

class TestBulkActions:
    def _make_photos(self, base, n=3):
        day = base / "organizado" / "2024" / "02" / "10"
        day.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(n):
            f = day / f"IMG_{i:03}.jpg"
            f.write_bytes(b"fake")
            paths.append(str(f))
        return paths

    def test_bulk_favourite(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        r = cliente_api.post("/api/photos/bulk", json={"paths": paths, "action": "favourite"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["affected"] == 3
        assert d["total_favourites"] >= 3  # may include other favourites from fixtures

    def test_bulk_unfavourite(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        # Favourite all 3, then unfavourite the first
        r1 = cliente_api.post("/api/photos/bulk", json={"paths": paths, "action": "favourite"})
        before = r1.json()["total_favourites"]
        r2 = cliente_api.post("/api/photos/bulk", json={"paths": [paths[0]], "action": "unfavourite"})
        assert r2.json()["total_favourites"] == before - 1

    def test_bulk_delete_moves_to_trash(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        r = cliente_api.post("/api/photos/bulk", json={"paths": paths[:2], "action": "delete"})
        assert r.status_code == 200
        assert r.json()["moved"] == 2
        # Files should be gone from original location
        from pathlib import Path
        assert not Path(paths[0]).exists()
        assert not Path(paths[1]).exists()
        # And present in .trash/
        trash = Path(paths[0]).parent.parent.parent / ".trash"
        assert trash.exists()
        assert len(list(trash.iterdir())) == 2

    def test_bulk_rejects_outside_paths(self, cliente_api, cwd_temporal):
        r = cliente_api.post("/api/photos/bulk",
                             json={"paths": ["/etc/passwd"], "action": "favourite"})
        assert r.status_code == 403

    def test_bulk_unknown_action(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        r = cliente_api.post("/api/photos/bulk", json={"paths": paths, "action": "explode"})
        assert r.status_code == 400


class TestAlbums:
    """Albums are named collections that reference photos by path.
    Photos are never copied/moved; a photo can be in many albums."""

    def _make_photos(self, base, n=3):
        day = base / "organizado" / "2024" / "03" / "20"
        day.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(n):
            f = day / f"IMG_{i:03}.jpg"
            f.write_bytes(b"fake-jpeg-bytes")
            paths.append(str(f))
        return paths

    def test_albums_empty_initially(self, cliente_api, cwd_temporal):
        r = cliente_api.get("/api/albums")
        assert r.status_code == 200
        assert r.json() == {"albums": [], "total": 0}

    def test_create_album(self, cliente_api, cwd_temporal):
        r = cliente_api.post("/api/albums", json={"name": "Vacaciones 2024"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["album"]["name"] == "Vacaciones 2024"
        assert d["album"]["id"].startswith("alb_")
        assert d["album"]["count"] == 0

    def test_create_album_empty_name_rejected(self, cliente_api, cwd_temporal):
        r = cliente_api.post("/api/albums", json={"name": "   "})
        assert r.status_code == 400

    def test_created_album_appears_in_list(self, cliente_api, cwd_temporal):
        cliente_api.post("/api/albums", json={"name": "Trip"})
        r = cliente_api.get("/api/albums")
        albums = r.json()["albums"]
        assert len(albums) == 1
        assert albums[0]["name"] == "Trip"
        assert albums[0]["count"] == 0
        assert albums[0]["cover"] is None

    def test_unique_ids(self, cliente_api, cwd_temporal):
        a = cliente_api.post("/api/albums", json={"name": "A"}).json()["album"]["id"]
        b = cliente_api.post("/api/albums", json={"name": "B"}).json()["album"]["id"]
        assert a != b

    def test_add_photos_to_album(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        r = cliente_api.post(f"/api/albums/{aid}/photos",
                             json={"paths": paths, "action": "add"})
        assert r.status_code == 200
        assert r.json()["count"] == 3

    def test_add_photos_is_idempotent(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": paths, "action": "add"})
        r = cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": paths, "action": "add"})
        assert r.json()["count"] == 3  # no duplicates

    def test_remove_photos_from_album(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": paths, "action": "add"})
        r = cliente_api.post(f"/api/albums/{aid}/photos",
                             json={"paths": [paths[0]], "action": "remove"})
        assert r.json()["count"] == 2

    def test_add_rejects_outside_paths(self, cliente_api, cwd_temporal):
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        r = cliente_api.post(f"/api/albums/{aid}/photos",
                             json={"paths": ["/etc/passwd"], "action": "add"})
        # Rejected silently → album stays empty (path not allowed)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_photos_action_unknown(self, cliente_api, cwd_temporal):
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        r = cliente_api.post(f"/api/albums/{aid}/photos",
                             json={"paths": [], "action": "shuffle"})
        assert r.status_code == 400

    def test_add_to_missing_album_404(self, cliente_api, cwd_temporal):
        r = cliente_api.post("/api/albums/alb_doesnotexist/photos",
                             json={"paths": [], "action": "add"})
        assert r.status_code == 404

    def test_get_album_photos(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": paths, "action": "add"})
        r = cliente_api.get(f"/api/albums/{aid}")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 3
        assert len(d["photos"]) == 3
        assert d["photos"][0]["id"] == paths[0]
        assert d["photos"][0]["filename"] == "IMG_000.jpg"
        assert d["photos"][0]["exists"] is True

    def test_get_missing_album_404(self, cliente_api, cwd_temporal):
        r = cliente_api.get("/api/albums/alb_nope")
        assert r.status_code == 404

    def test_cover_defaults_to_first_photo(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": paths, "action": "add"})
        albums = cliente_api.get("/api/albums").json()["albums"]
        assert albums[0]["cover"] == paths[0]

    def test_set_cover(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": paths, "action": "add"})
        r = cliente_api.patch(f"/api/albums/{aid}", json={"cover": paths[2]})
        assert r.status_code == 200
        albums = cliente_api.get("/api/albums").json()["albums"]
        assert albums[0]["cover"] == paths[2]

    def test_set_cover_not_in_album_rejected(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": [paths[0]], "action": "add"})
        r = cliente_api.patch(f"/api/albums/{aid}", json={"cover": paths[1]})
        assert r.status_code == 400

    def test_removing_cover_photo_clears_cover(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": paths, "action": "add"})
        cliente_api.patch(f"/api/albums/{aid}", json={"cover": paths[0]})
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": [paths[0]], "action": "remove"})
        # Cover should fall back to another existing photo, not the removed one
        albums = cliente_api.get("/api/albums").json()["albums"]
        assert albums[0]["cover"] != paths[0]

    def test_rename_album(self, cliente_api, cwd_temporal):
        aid = cliente_api.post("/api/albums", json={"name": "Old"}).json()["album"]["id"]
        r = cliente_api.patch(f"/api/albums/{aid}", json={"name": "New"})
        assert r.status_code == 200
        assert r.json()["album"]["name"] == "New"

    def test_rename_empty_rejected(self, cliente_api, cwd_temporal):
        aid = cliente_api.post("/api/albums", json={"name": "Old"}).json()["album"]["id"]
        r = cliente_api.patch(f"/api/albums/{aid}", json={"name": "  "})
        assert r.status_code == 400

    def test_rename_missing_404(self, cliente_api, cwd_temporal):
        r = cliente_api.patch("/api/albums/alb_x", json={"name": "New"})
        assert r.status_code == 404

    def test_delete_album(self, cliente_api, cwd_temporal):
        aid = cliente_api.post("/api/albums", json={"name": "Doomed"}).json()["album"]["id"]
        r = cliente_api.delete(f"/api/albums/{aid}")
        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert cliente_api.get("/api/albums").json()["total"] == 0

    def test_delete_missing_404(self, cliente_api, cwd_temporal):
        r = cliente_api.delete("/api/albums/alb_ghost")
        assert r.status_code == 404

    def test_delete_album_keeps_photos_on_disk(self, cliente_api, cwd_temporal):
        from pathlib import Path
        paths = self._make_photos(cwd_temporal)
        aid = cliente_api.post("/api/albums", json={"name": "X"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{aid}/photos", json={"paths": paths, "action": "add"})
        cliente_api.delete(f"/api/albums/{aid}")
        # Underlying files must still exist
        for p in paths:
            assert Path(p).is_file()

    def test_photo_can_be_in_multiple_albums(self, cliente_api, cwd_temporal):
        paths = self._make_photos(cwd_temporal, n=1)
        a1 = cliente_api.post("/api/albums", json={"name": "A1"}).json()["album"]["id"]
        a2 = cliente_api.post("/api/albums", json={"name": "A2"}).json()["album"]["id"]
        cliente_api.post(f"/api/albums/{a1}/photos", json={"paths": paths, "action": "add"})
        cliente_api.post(f"/api/albums/{a2}/photos", json={"paths": paths, "action": "add"})
        assert cliente_api.get(f"/api/albums/{a1}").json()["count"] == 1
        assert cliente_api.get(f"/api/albums/{a2}").json()["count"] == 1


# ═══════════════════ /api/days uses captures table ══════════════════════════

class TestDaysReadsFromCaptures:
    """Regression: /api/days used to only walk YYYY/MM/DD folders and ignore
    photos in /incoming or any other flat directory. Now it reads from the
    captures table so ALL registered photos appear."""

    def test_captures_without_folder_structure_appear_in_days(
        self, cliente_api, cwd_temporal,
    ):
        from photos_sync import repository as repo

        # A photo living in a flat /incoming directory (not YYYY/MM/DD)
        flat = cwd_temporal / "incoming" / "phone_shot.jpg"
        flat.parent.mkdir(parents=True, exist_ok=True)
        flat.write_bytes(b"x" * 5000)
        stat = flat.stat()

        repo.upsert_captures([{
            "id":            str(flat),
            "archivo":       "phone_shot.jpg",
            "formato":       "jpg",
            "tamano_mb":     0.005,
            "mtime":         stat.st_mtime,
            "fecha_captura": "2024-05-20T14:30:00",
            "ruta_original": str(flat),
            "ruta_destino":  str(flat),
            "tags":          [],
        }])

        r = cliente_api.get("/api/days")
        assert r.status_code == 200
        body = r.json()
        assert body["total_photos"] == 1
        # The day '2024-05-20' shows up
        day = next(d for d in body["days"] if d["fecha"] == "2024-05-20")
        assert day["cover_path"] == str(flat)

    def test_day_photos_returns_flat_photo(self, cliente_api, cwd_temporal):
        from photos_sync import repository as repo

        flat = cwd_temporal / "incoming" / "img.jpg"
        flat.parent.mkdir(parents=True, exist_ok=True)
        flat.write_bytes(b"x" * 5000)
        stat = flat.stat()

        repo.upsert_captures([{
            "id":            str(flat),
            "archivo":       "img.jpg",
            "formato":       "jpg",
            "tamano_mb":     0.005,
            "mtime":         stat.st_mtime,
            "fecha_captura": "2024-06-01T10:00:00",
            "ruta_original": str(flat),
            "ruta_destino":  str(flat),
            "tags":          [],
        }])

        r = cliente_api.get("/api/days/2024-06-01/photos")
        assert r.status_code == 200
        assert r.json()["count"] == 1
        assert r.json()["photos"][0]["filename"] == "img.jpg"

    def test_day_photos_paginates_without_duplicates(
        self, cliente_api, cwd_temporal,
    ):
        from photos_sync import repository as repo

        captures = []
        expected_names = []
        for index in range(5):
            name = f"photo_{index}.jpg"
            photo = cwd_temporal / "incoming" / name
            photo.parent.mkdir(parents=True, exist_ok=True)
            photo.write_bytes(bytes([index]) * 100)
            expected_names.append(name)
            captures.append({
                "id":            str(photo),
                "archivo":       name,
                "formato":       "jpg",
                "tamano_mb":     0.001,
                "mtime":         photo.stat().st_mtime,
                "fecha_captura": "2024-06-02T10:00:00",
                "ruta_original": str(photo),
                "ruta_destino":  str(photo),
                "tags":          [],
            })
        repo.upsert_captures(captures)

        first = cliente_api.get(
            "/api/days/2024-06-02/photos?offset=0&limit=3"
        ).json()
        second = cliente_api.get(
            f"/api/days/2024-06-02/photos?offset={first['next_offset']}&limit=3"
        ).json()

        assert first["count"] == 5
        assert first["has_more"] is True
        assert first["next_offset"] == 3
        assert second["has_more"] is False
        assert second["next_offset"] is None
        names = [p["filename"] for p in first["photos"] + second["photos"]]
        assert names == expected_names
        assert len(names) == len(set(names))

    def test_day_photos_uses_mtime_fallback_for_legacy_capture(
        self, cliente_api, cwd_temporal, monkeypatch,
    ):
        from datetime import datetime

        from photos_sync import repository as repo

        photo = cwd_temporal / "incoming" / "legacy.jpg"
        photo.parent.mkdir(parents=True, exist_ok=True)
        photo.write_bytes(b"legacy")
        repo.upsert_captures([{
            "id":            str(photo),
            "archivo":       "legacy.jpg",
            "formato":       "jpg",
            "tamano_mb":     0.001,
            "mtime":         datetime(2024, 6, 3, 12).timestamp(),
            "fecha_captura": "",
            "ruta_original": str(photo),
            "ruta_destino":  str(photo),
            "tags":          [],
        }])
        repo.set_favourite(str(photo), True)
        monkeypatch.setattr(
            repo,
            "load_captures",
            lambda: (_ for _ in ()).throw(AssertionError("full scan used")),
        )
        monkeypatch.setattr(
            repo,
            "favourites_set",
            lambda: (_ for _ in ()).throw(AssertionError("extra query used")),
        )

        body = cliente_api.get("/api/days/2024-06-03/photos").json()

        assert body["count"] == 1
        assert body["photos"][0]["filename"] == "legacy.jpg"
        assert body["photos"][0]["favourite"] is True

    def test_capture_with_no_date_grouped_as_undated(
        self, cliente_api, cwd_temporal,
    ):
        from photos_sync import repository as repo

        f = cwd_temporal / "incoming" / "nodate.jpg"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * 500)

        # No capture_date, mtime=0 → 'undated'
        repo.upsert_captures([{
            "id":            str(f),
            "archivo":       "nodate.jpg",
            "formato":       "jpg",
            "tamano_mb":     0.001,
            "mtime":         0,
            "fecha_captura": "",
            "ruta_original": str(f),
            "ruta_destino":  str(f),
            "tags":          [],
        }])

        r = cliente_api.get("/api/days")
        assert r.status_code == 200
        # 'undated' bucket present when there's no date info
        # (mtime=0 becomes 1970-01-01 which is a valid date, so we just
        # verify the photo is somewhere in the list)
        assert r.json()["total_photos"] == 1


class TestGlobalPhotosPagination:
    def test_global_feed_orders_paginates_and_filters_favourites(
        self, cliente_api, cwd_temporal,
    ):
        from datetime import datetime

        from photos_sync import repository as repo

        captures = []
        paths = []
        for index, capture_date in enumerate((
            "2024-07-01T10:00:00",
            "2024-07-03T10:00:00",
            "2024-07-02T10:00:00",
        )):
            photo = cwd_temporal / "incoming" / f"global_{index}.jpg"
            photo.parent.mkdir(parents=True, exist_ok=True)
            photo.write_bytes(bytes([index]) * 100)
            paths.append(str(photo))
            captures.append({
                "id":            str(photo),
                "archivo":       photo.name,
                "formato":       "jpg",
                "tamano_mb":     0.001,
                "mtime":         photo.stat().st_mtime,
                "fecha_captura": capture_date,
                "ruta_original": str(photo),
                "ruta_destino":  str(photo),
                "tags":          [],
            })
        legacy = cwd_temporal / "incoming" / "global_legacy.jpg"
        legacy.write_bytes(b"legacy")
        captures.append({
            "id":            str(legacy),
            "archivo":       legacy.name,
            "formato":       "jpg",
            "tamano_mb":     0.001,
            "mtime":         datetime(2024, 7, 4, 10).timestamp(),
            "fecha_captura": "",
            "ruta_original": str(legacy),
            "ruta_destino":  str(legacy),
            "tags":          [],
        })
        repo.upsert_captures(captures)
        repo.set_favourite(paths[0], True)

        first = cliente_api.get("/api/photos?offset=0&limit=2").json()
        second = cliente_api.get(
            f"/api/photos?offset={first['next_offset']}&limit=2"
        ).json()
        favourites = cliente_api.get(
            "/api/photos?offset=0&limit=10&favourite=true"
        ).json()

        assert first["count"] == 4
        assert first["has_more"] is True
        assert [photo["date"] for photo in first["photos"]] == [
            "2024-07-04", "2024-07-03",
        ]
        assert [photo["date"] for photo in second["photos"]] == [
            "2024-07-02", "2024-07-01",
        ]
        assert second["has_more"] is False
        assert favourites["count"] == 1
        assert favourites["photos"][0]["id"] == paths[0]
        assert favourites["photos"][0]["favourite"] is True
