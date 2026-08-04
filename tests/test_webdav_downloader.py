"""
Tests for photos_sync.storage.webdav_downloader.
────────────────────────────────────────────────
The HTTP layer (requests) is mocked, so no real WebDAV server is needed.
Covers PROPFIND parsing, file collection, download-to-local (with resume
and dedup), and the high-level sync helper.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from photos_sync.storage import webdav_downloader as wd

# ── PROPFIND XML fixtures ─────────────────────────────────────────────────────

def _propfind_xml(entries):
    """Build a WebDAV multistatus XML from (href, is_dir, size) tuples."""
    parts = ['<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">']
    for href, is_dir, size in entries:
        rtype = "<d:collection/>" if is_dir else ""
        parts.append(
            f'<d:response><d:href>{href}</d:href>'
            f'<d:propstat><d:prop>'
            f'<d:resourcetype>{rtype}</d:resourcetype>'
            f'<d:getcontentlength>{size}</d:getcontentlength>'
            f'<d:getlastmodified>Mon, 01 Jan 2024 00:00:00 GMT</d:getlastmodified>'
            f'</d:prop></d:propstat></d:response>'
        )
    parts.append("</d:multistatus>")
    return "".join(parts).encode()


def _mock_response(status=207, content=b""):
    r = MagicMock()
    r.status_code = status
    r.content = content
    return r


# ── RemoteFile dataclass ──────────────────────────────────────────────────────

class TestRemoteFile:
    def test_construction(self):
        f = wd.RemoteFile(href="/a/b.jpg", name="b.jpg", size=100, modified="x")
        assert f.name == "b.jpg"
        assert f.size == 100


# ── list_remote_files ─────────────────────────────────────────────────────────

class TestListRemoteFiles:
    def test_lists_photos_in_directory(self):
        xml = _propfind_xml([
            ("/Pictures/Screenshots/", True, 0),
            ("/Pictures/Screenshots/IMG_001.jpg", False, 1000),
            ("/Pictures/Screenshots/IMG_002.png", False, 2000),
        ])
        with patch.object(wd, "_requests") as mock_req:
            mock_req.request.return_value = _mock_response(207, xml)
            files = wd.list_remote_files("1.2.3.4", 8080, "/Pictures/Screenshots")
        names = sorted(f.name for f in files)
        assert names == ["IMG_001.jpg", "IMG_002.png"]

    def test_skips_non_photo_files(self):
        xml = _propfind_xml([
            ("/x/", True, 0),
            ("/x/photo.jpg", False, 100),
            ("/x/document.txt", False, 50),
            ("/x/notes.pdf", False, 50),
        ])
        with patch.object(wd, "_requests") as mock_req:
            mock_req.request.return_value = _mock_response(207, xml)
            files = wd.list_remote_files("1.2.3.4", 8080, "/x")
        assert [f.name for f in files] == ["photo.jpg"]

    def test_captures_file_size(self):
        xml = _propfind_xml([
            ("/x/", True, 0),
            ("/x/big.jpg", False, 5000),
        ])
        with patch.object(wd, "_requests") as mock_req:
            mock_req.request.return_value = _mock_response(207, xml)
            files = wd.list_remote_files("1.2.3.4", 8080, "/x")
        assert files[0].size == 5000

    def test_empty_on_bad_status(self):
        with patch.object(wd, "_requests") as mock_req:
            mock_req.request.return_value = _mock_response(404, b"")
            files = wd.list_remote_files("1.2.3.4", 8080, "/nope")
        assert files == []

    def test_empty_on_request_exception(self):
        with patch.object(wd, "_requests") as mock_req:
            mock_req.request.side_effect = Exception("connection refused")
            files = wd.list_remote_files("1.2.3.4", 8080, "/x")
        assert files == []


# ── download_to_local ─────────────────────────────────────────────────────────

class TestDownloadToLocal:
    def test_downloads_file(self, tmp_path):
        files = [wd.RemoteFile(href="/x/a.jpg", name="a.jpg", size=5, modified="")]

        def fake_get(url, stream=True, timeout=60):
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.iter_content = lambda chunk_size: [b"hello"]
            return r

        with patch.object(wd, "_requests") as mock_req:
            mock_req.get.side_effect = fake_get
            out = wd.download_to_local("1.2.3.4", 8080, files, tmp_path)

        assert len(out) == 1
        assert (tmp_path / "a.jpg").read_bytes() == b"hello"

    def test_skips_existing_same_size(self, tmp_path):
        # Pre-create a file with the exact expected size
        (tmp_path / "a.jpg").write_bytes(b"12345")  # 5 bytes
        files = [wd.RemoteFile(href="/x/a.jpg", name="a.jpg", size=5, modified="")]

        with patch.object(wd, "_requests") as mock_req:
            out = wd.download_to_local("1.2.3.4", 8080, files, tmp_path)
            # Should not have called get at all
            mock_req.get.assert_not_called()
        assert len(out) == 1

    def test_calls_progress_callback(self, tmp_path):
        files = [
            wd.RemoteFile(href="/x/a.jpg", name="a.jpg", size=3, modified=""),
            wd.RemoteFile(href="/x/b.jpg", name="b.jpg", size=3, modified=""),
        ]
        calls = []

        def fake_get(url, stream=True, timeout=60):
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.iter_content = lambda chunk_size: [b"abc"]
            return r

        with patch.object(wd, "_requests") as mock_req:
            mock_req.get.side_effect = fake_get
            wd.download_to_local("1.2.3.4", 8080, files, tmp_path,
                                 on_progress=lambda c, t, n: calls.append((c, t, n)))
        assert len(calls) == 2
        assert calls[-1][0] == 2  # current
        assert calls[-1][1] == 2  # total

    def test_continues_on_download_error(self, tmp_path):
        files = [
            wd.RemoteFile(href="/x/bad.jpg", name="bad.jpg", size=3, modified=""),
            wd.RemoteFile(href="/x/good.jpg", name="good.jpg", size=3, modified=""),
        ]

        def fake_get(url, stream=True, timeout=60):
            r = MagicMock()
            if "bad" in url:
                r.raise_for_status.side_effect = Exception("500 error")
            else:
                r.raise_for_status = MagicMock()
                r.iter_content = lambda chunk_size: [b"abc"]
            return r

        with patch.object(wd, "_requests") as mock_req:
            mock_req.get.side_effect = fake_get
            wd.download_to_local("1.2.3.4", 8080, files, tmp_path)
        # good.jpg downloaded, bad.jpg skipped
        assert (tmp_path / "good.jpg").exists()
        assert not (tmp_path / "bad.jpg").exists()

    def test_creates_dest_dir(self, tmp_path):
        dest = tmp_path / "new" / "sub"
        files = []
        with patch.object(wd, "_requests"):
            wd.download_to_local("1.2.3.4", 8080, files, dest)
        assert dest.is_dir()


# ── sync_webdav_connection ────────────────────────────────────────────────────

class TestSyncWebDAVConnection:
    def test_scans_all_default_paths_and_downloads(self, tmp_path):
        xml = _propfind_xml([
            ("/Pictures/Screenshots/", True, 0),
            ("/Pictures/Screenshots/IMG_001.jpg", False, 3),
        ])

        def fake_get(url, stream=True, timeout=60):
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.iter_content = lambda chunk_size: [b"abc"]
            return r

        with patch.object(wd, "_requests") as mock_req:
            mock_req.request.return_value = _mock_response(207, xml)
            mock_req.get.side_effect = fake_get
            out = wd.sync_webdav_connection("1.2.3.4", 8080, tmp_path,
                                            remote_paths=["/Pictures/Screenshots"])
        assert len(out) == 1

    def test_returns_empty_when_no_photos(self, tmp_path):
        with patch.object(wd, "_requests") as mock_req:
            mock_req.request.return_value = _mock_response(207, _propfind_xml([]))
            out = wd.sync_webdav_connection("1.2.3.4", 8080, tmp_path,
                                            remote_paths=["/empty"])
        assert out == []

    def test_deduplicates_across_paths(self, tmp_path):
        # Same filename appears in two scanned paths → downloaded once
        xml = _propfind_xml([
            ("/a/", True, 0),
            ("/a/dup.jpg", False, 3),
        ])

        def fake_get(url, stream=True, timeout=60):
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.iter_content = lambda chunk_size: [b"abc"]
            return r

        with patch.object(wd, "_requests") as mock_req:
            mock_req.request.return_value = _mock_response(207, xml)
            mock_req.get.side_effect = fake_get
            out = wd.sync_webdav_connection("1.2.3.4", 8080, tmp_path,
                                            remote_paths=["/a", "/a"])
        # dup.jpg only downloaded once despite two paths
        assert len(out) == 1


