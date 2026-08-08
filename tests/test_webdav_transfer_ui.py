from __future__ import annotations

from pathlib import Path

UI = Path(__file__).parents[1] / "photos_sync/web/static/index.html"


def test_webdav_screen_shows_per_file_transfer_activity() -> None:
    html = UI.read_text(encoding="utf-8")

    assert 'id="wd-transfer-card"' in html
    assert 'id="wd-active-files"' in html
    assert 'id="wd-recent-files"' in html
    assert 'id="wd-failed-files"' in html
    assert "Transferring now" in html


def test_webdav_screen_can_retry_only_failed_photos() -> None:
    html = UI.read_text(encoding="utf-8")

    assert 'id="btn-wd-retry"' in html
    assert "Retry failed only" in html
    assert "/api/webdav/download/retry-failed" in html
    assert "renderWebDavTransfer" in html


def test_webdav_screen_can_exclude_mp4_videos() -> None:
    html = UI.read_text(encoding="utf-8")

    assert 'id="wd-include-videos"' in html
    assert 'id="wd-include-videos" type="checkbox"' in html
    assert "include_videos:includeVideos" in html
    assert "Include videos" in html
