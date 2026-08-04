"""
Tests for GAL-4: trash / recycle bin.
────────────────────────────────────
Covers: soft delete records to trash, list, restore, permanent delete,
empty trash, purge-old, and authorization.
"""
from __future__ import annotations

from pathlib import Path


def _make_photo(tmp_path: Path, name: str = "IMG_001.jpg") -> str:
    f = tmp_path / "organizado" / "2024" / "05" / "20" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"FAKE_IMAGE")
    return str(f)


def _delete_photo(client, path: str):
    return client.post("/api/photos/bulk", json={"paths": [path], "action": "delete"})


class TestTrashBasics:
    def test_trash_empty_initially(self, cliente_api, cwd_temporal):
        r = cliente_api.get("/api/trash")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_deleting_photo_adds_to_trash(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        _delete_photo(cliente_api, p)
        r = cliente_api.get("/api/trash")
        assert r.json()["total"] == 1
        assert r.json()["trash"][0]["filename"] == "IMG_001.jpg"

    def test_deleted_file_physically_moved(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        _delete_photo(cliente_api, p)
        # Original gone, file now in .trash
        assert not Path(p).exists()
        trash_path = cliente_api.get("/api/trash").json()["trash"][0]["trash_path"]
        assert Path(trash_path).is_file()

    def test_trash_entry_has_original_path(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        _delete_photo(cliente_api, p)
        entry = cliente_api.get("/api/trash").json()["trash"][0]
        assert entry["original_path"] == p


class TestRestore:
    def test_restore_puts_file_back(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        _delete_photo(cliente_api, p)
        entry_id = cliente_api.get("/api/trash").json()["trash"][0]["id"]

        r = cliente_api.post("/api/trash/restore", json={"ids": [entry_id]})
        assert r.status_code == 200
        assert r.json()["restored"] == 1
        # File is back at the original location
        assert Path(p).is_file()

    def test_restore_removes_from_trash(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        _delete_photo(cliente_api, p)
        entry_id = cliente_api.get("/api/trash").json()["trash"][0]["id"]
        cliente_api.post("/api/trash/restore", json={"ids": [entry_id]})
        assert cliente_api.get("/api/trash").json()["total"] == 0

    def test_restore_multiple(self, cliente_api, cwd_temporal):
        p1 = _make_photo(cwd_temporal, "A.jpg")
        p2 = _make_photo(cwd_temporal, "B.jpg")
        _delete_photo(cliente_api, p1)
        _delete_photo(cliente_api, p2)
        ids = [e["id"] for e in cliente_api.get("/api/trash").json()["trash"]]
        r = cliente_api.post("/api/trash/restore", json={"ids": ids})
        assert r.json()["restored"] == 2

    def test_restore_when_original_exists_uses_suffix(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal, "dup.jpg")
        _delete_photo(cliente_api, p)
        # Recreate a file at the original path
        Path(p).write_bytes(b"NEW_FILE")
        entry_id = cliente_api.get("/api/trash").json()["trash"][0]["id"]
        r = cliente_api.post("/api/trash/restore", json={"ids": [entry_id]})
        assert r.json()["restored"] == 1
        # Restored copy lives alongside with _restored suffix
        restored = Path(p).parent / "dup_restored.jpg"
        assert restored.is_file()


class TestPermanentDelete:
    def test_delete_forever_removes_file(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        _delete_photo(cliente_api, p)
        entry = cliente_api.get("/api/trash").json()["trash"][0]
        trash_path = entry["trash_path"]

        r = cliente_api.post("/api/trash/delete", json={"ids": [entry["id"]]})
        assert r.json()["deleted"] == 1
        assert not Path(trash_path).exists()
        assert cliente_api.get("/api/trash").json()["total"] == 0

    def test_empty_trash(self, cliente_api, cwd_temporal):
        for n in ("A.jpg", "B.jpg", "C.jpg"):
            _delete_photo(cliente_api, _make_photo(cwd_temporal, n))
        assert cliente_api.get("/api/trash").json()["total"] == 3

        r = cliente_api.post("/api/trash/empty")
        assert r.json()["deleted"] == 3
        assert cliente_api.get("/api/trash").json()["total"] == 0


class TestPurgeOld:
    def test_purge_old_removes_aged_entries(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        _delete_photo(cliente_api, p)
        # Backdate the entry to 40 days ago
        from datetime import datetime, timedelta

        from sqlalchemy import update

        from photos_sync.db import get_engine, t_trash
        old_date = (datetime.now() - timedelta(days=40)).isoformat(timespec="seconds")
        with get_engine().begin() as conn:
            conn.execute(update(t_trash).values(deleted_at=old_date))

        r = cliente_api.post("/api/trash/purge-old?days=30")
        assert r.status_code == 200
        assert r.json()["purged"] == 1
        assert cliente_api.get("/api/trash").json()["total"] == 0

    def test_purge_keeps_recent(self, cliente_api, cwd_temporal):
        p = _make_photo(cwd_temporal)
        _delete_photo(cliente_api, p)
        r = cliente_api.post("/api/trash/purge-old?days=30")
        assert r.json()["purged"] == 0
        assert cliente_api.get("/api/trash").json()["total"] == 1


class TestTrashAuthorization:
    def test_anon_cannot_view_trash(self, cliente_anon, cwd_temporal):
        cliente_anon.post("/api/auth/setup-admin",
                          json={"username": "root", "password": "rootpass1"})
        cliente_anon.post("/api/auth/logout")
        r = cliente_anon.get("/api/trash")
        assert r.status_code == 401

    def test_user_can_use_trash(self, cliente_user, cwd_temporal):
        # Normal user can view trash (shared library)
        r = cliente_user.get("/api/trash")
        assert r.status_code == 200

    def test_purge_old_is_admin_only(self, cliente_user, cwd_temporal):
        r = cliente_user.post("/api/trash/purge-old?days=30")
        assert r.status_code == 403
