"""
Tests for GAL-5: photo download-zip endpoint.
────────────────────────────────────────────
Covers: single photo, multiple photos, deduplication of names,
security (paths outside allowed bases rejected), edge cases.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

# ── Helper ────────────────────────────────────────────────────────────────────

def _make_photo(tmp_path: Path, name: str = "IMG_001.jpg",
                content: bytes = b"JPEG_PLACEHOLDER") -> str:
    """Create a fake photo file and return its absolute path."""
    f = tmp_path / "organizado" / "2024" / "05" / "20" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(content)
    return str(f)


def _zip_names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return sorted(z.namelist())


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDownloadZip:
    def test_download_single_photo_returns_zip(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        r = cliente_api.get(f"/api/photos/download-zip?paths={p}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"

    def test_zip_contains_correct_filename(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal, "vacation.jpg")
        r = cliente_api.get(f"/api/photos/download-zip?paths={p}")
        assert "vacation.jpg" in _zip_names(r.content)

    def test_zip_file_content_matches_original(self, cliente_api, cwd_temporal):
        content = b"FAKE_IMAGE_DATA_12345"
        p = _make_photo(cwd_temporal, "photo.jpg", content)
        r = cliente_api.get(f"/api/photos/download-zip?paths={p}")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            assert z.read("photo.jpg") == content

    def test_multiple_photos_all_in_zip(self, cliente_api, cwd_temporal):
        p1 = _make_photo(cwd_temporal, "IMG_001.jpg", b"data1")
        p2 = _make_photo(cwd_temporal, "IMG_002.jpg", b"data2")
        p3 = _make_photo(cwd_temporal, "IMG_003.jpg", b"data3")
        paths = ",".join([p1, p2, p3])
        r = cliente_api.get(f"/api/photos/download-zip?paths={paths}")
        assert r.status_code == 200
        names = _zip_names(r.content)
        assert "IMG_001.jpg" in names
        assert "IMG_002.jpg" in names
        assert "IMG_003.jpg" in names

    def test_content_disposition_header(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        r = cliente_api.get(f"/api/photos/download-zip?paths={p}")
        assert "attachment" in r.headers["content-disposition"]
        assert ".zip" in r.headers["content-disposition"]

    def test_filename_includes_photo_count(self, cliente_api, cwd_temporal):
        p1 = _make_photo(cwd_temporal, "A.jpg")
        p2 = _make_photo(cwd_temporal, "B.jpg")
        paths = f"{p1},{p2}"
        r = cliente_api.get(f"/api/photos/download-zip?paths={paths}")
        assert "2" in r.headers["content-disposition"]

    def test_duplicate_filenames_are_deduplicated(self, cliente_api, cwd_temporal):
        """Two photos with the same filename must not overwrite each other in ZIP."""
        # Create two photos with the same name in different subdirs
        dir1 = cwd_temporal / "organizado" / "2024" / "01" / "01"
        dir2 = cwd_temporal / "organizado" / "2024" / "02" / "01"
        dir1.mkdir(parents=True, exist_ok=True)
        dir2.mkdir(parents=True, exist_ok=True)
        p1 = str(dir1 / "photo.jpg"); Path(p1).write_bytes(b"v1")
        p2 = str(dir2 / "photo.jpg"); Path(p2).write_bytes(b"v2")

        r = cliente_api.get(f"/api/photos/download-zip?paths={p1},{p2}")
        assert r.status_code == 200
        names = _zip_names(r.content)
        assert len(names) == 2  # both files present
        assert len(set(names)) == 2  # with distinct names

    def test_missing_file_is_skipped_silently(self, cliente_api, cwd_temporal):
        good = _make_photo(cwd_temporal, "real.jpg")
        bad = str(cwd_temporal / "organizado" / "2024" / "05" / "20" / "ghost.jpg")
        r = cliente_api.get(f"/api/photos/download-zip?paths={good},{bad}")
        assert r.status_code == 200
        names = _zip_names(r.content)
        assert "real.jpg" in names
        assert "ghost.jpg" not in names

    def test_outside_path_rejected_403(self, cliente_api, cwd_temporal):
        r = cliente_api.get("/api/photos/download-zip?paths=/etc/passwd")
        assert r.status_code in (403, 404)

    def test_all_outside_paths_returns_404(self, cliente_api, cwd_temporal):
        r = cliente_api.get(
            "/api/photos/download-zip?paths=/etc/passwd,/etc/shadow"
        )
        assert r.status_code in (403, 404)

    def test_unauthenticated_returns_401(self, cliente_anon, cwd_temporal):
        # Need an admin to exist for the 401 to be meaningful
        cliente_anon.post("/api/auth/setup-admin",
                          json={"username": "root", "password": "rootpass1"})
        cliente_anon.post("/api/auth/logout")
        p = _make_photo(cwd_temporal)
        r = cliente_anon.get(f"/api/photos/download-zip?paths={p}")
        assert r.status_code == 401

    def test_empty_paths_returns_error(self, cliente_api, cwd_temporal):
        r = cliente_api.get("/api/photos/download-zip?paths=")
        assert r.status_code in (400, 403, 404, 422)

    def test_zip_is_valid_archive(self, cliente_api, cwd_temporal):
        p1 = _make_photo(cwd_temporal, "a.jpg", b"aaa")
        p2 = _make_photo(cwd_temporal, "b.jpg", b"bbb")
        r = cliente_api.get(f"/api/photos/download-zip?paths={p1},{p2}")
        assert zipfile.is_zipfile(io.BytesIO(r.content))
