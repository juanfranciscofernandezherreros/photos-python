"""
End-to-end integration test for /api/webdav/download.

NO MOCKS. This test:
  1. Starts a real HTTP server in a background thread that speaks WebDAV
     (PROPFIND returns multistatus XML; GET returns real file bytes).
  2. Points the FastAPI endpoint at that real server via real IP:port.
  3. Verifies the downloaded files land on disk AND that captures rows
     are actually written to the (real, in-memory) SQLite database.

If this test passes, the real code path — sync_webdav_connection →
download_to_local → repo.upsert_captures → get_capture_by_dest — is
correct end to end. Any failure in Docker after this passes is
environmental (image not rebuilt, DB not reachable, wrong port).
"""
from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

# ── Real WebDAV-ish HTTP server ────────────────────────────────────────────

class _WebDAVHandler(BaseHTTPRequestHandler):
    """Minimal handler that answers PROPFIND (returns XML listing of a
    hard-coded set of files) and GET (returns real bytes for those files)."""

    files = {
        "/DCIM/Camera/IMG_1000.jpg": b"real-bytes-of-image-one" * 5000,   # ~110 KB
        "/DCIM/Camera/IMG_1001.jpg": b"real-bytes-of-image-two" * 5000,
        "/DCIM/Camera/IMG_1002.png": b"png-payload-here" * 8000,          # ~130 KB
    }
    activity_lock = threading.Lock()
    active_gets = 0
    max_active_gets = 0
    fail_paths: set[str] = set()
    range_requests: list[tuple[str, int]] = []

    def log_message(self, *a, **kw):
        pass  # silence stderr spam in tests

    def do_PROPFIND(self):
        path = self.path.rstrip("/") or "/DCIM/Camera"
        # Only respond with contents when the client asks for the folder that
        # actually has our fixtures. Return empty multistatus for other paths.
        parts = ['<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">']
        if path in ("/DCIM/Camera", "/DCIM/Camera/"):
            parts.append(
                '<d:response><d:href>/DCIM/Camera/</d:href>'
                '<d:propstat><d:prop>'
                '<d:resourcetype><d:collection/></d:resourcetype>'
                '<d:getcontentlength>0</d:getcontentlength>'
                '<d:getlastmodified>Mon, 01 Jan 2024 00:00:00 GMT</d:getlastmodified>'
                '</d:prop></d:propstat></d:response>'
            )
            for href, content in self.files.items():
                parts.append(
                    f'<d:response><d:href>{href}</d:href>'
                    f'<d:propstat><d:prop>'
                    f'<d:resourcetype></d:resourcetype>'
                    f'<d:getcontentlength>{len(content)}</d:getcontentlength>'
                    f'<d:getlastmodified>Mon, 01 Jan 2024 00:00:00 GMT</d:getlastmodified>'
                    f'</d:prop></d:propstat></d:response>'
                )
        parts.append('</d:multistatus>')
        body = "".join(parts).encode()
        self.send_response(207)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        content = self.files.get(self.path)
        if content is None:
            self.send_response(404); self.end_headers(); return
        if self.path in self.fail_paths:
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        range_header = self.headers.get("Range", "")
        start = 0
        if range_header.startswith("bytes="):
            start = int(range_header.removeprefix("bytes=").split("-", 1)[0])
            type(self).range_requests.append((self.path, start))
            content = content[start:]
        with self.activity_lock:
            type(self).active_gets += 1
            type(self).max_active_gets = max(
                type(self).max_active_gets,
                type(self).active_gets,
            )
        try:
            time.sleep(0.05)
            self.send_response(206 if start else 200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(content)))
            if start:
                total = len(type(self).files[self.path])
                self.send_header("Content-Range", f"bytes {start}-{total - 1}/{total}")
            self.end_headers()
            self.wfile.write(content)
        finally:
            with self.activity_lock:
                type(self).active_gets -= 1


@pytest.fixture()
def webdav_server():
    """Start a real HTTP server on a free port for the test's lifetime."""
    # Pick a free port
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    _WebDAVHandler.active_gets = 0
    _WebDAVHandler.max_active_gets = 0
    _WebDAVHandler.fail_paths = set()
    _WebDAVHandler.range_requests = []
    srv = ThreadingHTTPServer(("127.0.0.1", port), _WebDAVHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    # Wait briefly for the socket to be ready
    time.sleep(0.05)
    yield "127.0.0.1", port
    srv.shutdown(); srv.server_close()


# ── The actual end-to-end test ─────────────────────────────────────────────

class TestWebDAVEndToEnd:
    """These tests hit the real POST /api/webdav/download endpoint with a
    real HTTP server behind it and verify rows land in the real DB."""

    def test_full_download_persists_to_captures(
        self, cliente_api, cwd_temporal, webdav_server,
    ):
        import time

        from photos_sync import repository as repo
        from photos_sync.storage import webdav_downloader as wd

        host, port = webdav_server
        dest = cwd_temporal / "incoming"
        repo.save_destination_local(str(cwd_temporal))

        original_paths = wd.DEFAULT_REMOTE_PATHS[:]
        wd.DEFAULT_REMOTE_PATHS = ["/DCIM/Camera"]
        try:
            # Kick off the background download
            r = cliente_api.post("/api/webdav/download", json={
                "ip":          host,
                "port":        str(port),
                "dest_folder": str(dest),
            })
            assert r.status_code == 200
            assert r.json()["started"] is True

            # Poll until done (max 20s)
            for _ in range(200):
                s = cliente_api.get("/api/webdav/download-status").json()
                if s["done"]:
                    break
                time.sleep(0.1)
        finally:
            wd.DEFAULT_REMOTE_PATHS = original_paths

        assert s["done"] is True
        assert s["error"] is None
        assert s["downloaded"] == 3
        assert s["registered"] == 3
        assert s["workers"] >= 2
        assert _WebDAVHandler.max_active_gets >= 2
        assert s["active_files"] == {}
        assert s["failed_files"] == []
        assert len(s["recent_files"]) == 3

        # Files on disk
        assert (dest / "IMG_1000.jpg").is_file()
        assert (dest / "IMG_1000.jpg").read_bytes().startswith(b"real-bytes-of-image-one")

        # Rows in captures
        assert repo.get_capture_by_dest(str(dest / "IMG_1000.jpg")) is not None
        assert len(repo.load_captures()) == 3

    def test_second_call_is_idempotent(
        self, cliente_api, cwd_temporal, webdav_server,
    ):
        import time

        from photos_sync import repository as repo
        from photos_sync.storage import webdav_downloader as wd

        host, port = webdav_server
        dest = cwd_temporal / "incoming"
        repo.save_destination_local(str(cwd_temporal))

        original_paths = wd.DEFAULT_REMOTE_PATHS[:]
        wd.DEFAULT_REMOTE_PATHS = ["/DCIM/Camera"]
        try:
            # First run
            cliente_api.post("/api/webdav/download", json={
                "ip": host, "port": str(port), "dest_folder": str(dest),
            })
            for _ in range(200):
                if cliente_api.get("/api/webdav/download-status").json()["done"]:
                    break
                time.sleep(0.1)

            # Second run — files exist, should all be skipped-as-same-size
            cliente_api.post("/api/webdav/download", json={
                "ip": host, "port": str(port), "dest_folder": str(dest),
            })
            for _ in range(200):
                s = cliente_api.get("/api/webdav/download-status").json()
                if s["done"]:
                    break
                time.sleep(0.1)
        finally:
            wd.DEFAULT_REMOTE_PATHS = original_paths

        # Same-size files were skipped on the second run — but they were already
        # registered from the first, so no duplicates.
        assert len(repo.load_captures()) == 3

    def test_downloaded_files_show_in_diag_endpoint(
        self, cliente_api, cwd_temporal, webdav_server,
    ):
        """The /api/diag counts must reflect the downloaded photos."""
        import time

        from photos_sync import repository as repo
        from photos_sync.storage import webdav_downloader as wd

        host, port = webdav_server
        dest = cwd_temporal / "incoming"
        repo.save_destination_local(str(cwd_temporal))

        original_paths = wd.DEFAULT_REMOTE_PATHS[:]
        wd.DEFAULT_REMOTE_PATHS = ["/DCIM/Camera"]
        try:
            cliente_api.post("/api/webdav/download", json={
                "ip": host, "port": str(port), "dest_folder": str(dest),
            })
            for _ in range(200):
                if cliente_api.get("/api/webdav/download-status").json()["done"]:
                    break
                time.sleep(0.1)
        finally:
            wd.DEFAULT_REMOTE_PATHS = original_paths

        diag = cliente_api.get("/api/diag").json()
        assert diag["counts"]["captures"] == 3

    def test_failed_photo_is_visible_and_can_be_retried_alone(
        self, cliente_api, cwd_temporal, webdav_server,
    ):
        from photos_sync import repository as repo
        from photos_sync.storage import webdav_downloader as wd

        host, port = webdav_server
        dest = cwd_temporal / "incoming"
        repo.save_destination_local(str(cwd_temporal))
        failed_path = "/DCIM/Camera/IMG_1001.jpg"
        _WebDAVHandler.fail_paths = {failed_path}
        original_paths = wd.DEFAULT_REMOTE_PATHS[:]
        wd.DEFAULT_REMOTE_PATHS = ["/DCIM/Camera"]
        try:
            response = cliente_api.post("/api/webdav/download", json={
                "ip": host, "port": str(port), "dest_folder": str(dest),
            })
            assert response.status_code == 200
            for _ in range(200):
                status = cliente_api.get("/api/webdav/download-status").json()
                if status["done"]:
                    break
                time.sleep(0.1)

            assert status["failed"] == 1
            assert status["retry_available"] is True
            assert status["failed_files"][0]["href"] == failed_path
            assert status["failed_files"][0]["name"] == "IMG_1001.jpg"
            assert "503" in status["failed_files"][0]["error"]

            _WebDAVHandler.fail_paths.clear()
            retry = cliente_api.post("/api/webdav/download/retry-failed")
            assert retry.status_code == 200
            assert retry.json()["retrying"] is True
            for _ in range(200):
                status = cliente_api.get("/api/webdav/download-status").json()
                if status["done"]:
                    break
                time.sleep(0.1)
        finally:
            wd.DEFAULT_REMOTE_PATHS = original_paths
            _WebDAVHandler.fail_paths.clear()

        assert status["total"] == 1
        assert status["failed"] == 0
        assert status["downloaded"] == 1
        assert status["retry_available"] is False
        assert (dest / "IMG_1001.jpg").is_file()
        assert len(repo.load_captures()) == 3

    def test_existing_partial_file_is_resumed_with_http_range(
        self, cliente_api, cwd_temporal, webdav_server,
    ):
        from photos_sync import repository as repo
        from photos_sync.storage import webdav_downloader as wd

        host, port = webdav_server
        dest = cwd_temporal / "incoming"
        dest.mkdir(parents=True)
        repo.save_destination_local(str(cwd_temporal))
        remote_path = "/DCIM/Camera/IMG_1000.jpg"
        content = _WebDAVHandler.files[remote_path]
        resume_at = len(content) // 2
        partial = dest / "IMG_1000.jpg.webdav.part"
        partial.write_bytes(content[:resume_at])

        original_paths = wd.DEFAULT_REMOTE_PATHS[:]
        wd.DEFAULT_REMOTE_PATHS = ["/DCIM/Camera"]
        try:
            response = cliente_api.post("/api/webdav/download", json={
                "ip": host, "port": str(port), "dest_folder": str(dest),
            })
            assert response.status_code == 200
            for _ in range(200):
                status = cliente_api.get("/api/webdav/download-status").json()
                if status["done"]:
                    break
                time.sleep(0.1)
        finally:
            wd.DEFAULT_REMOTE_PATHS = original_paths

        assert status["failed"] == 0
        assert status["resumed"] == 1
        assert (remote_path, resume_at) in _WebDAVHandler.range_requests
        assert (dest / "IMG_1000.jpg").read_bytes() == content
        assert not partial.exists()
