"""Contract tests for the overview dashboard."""

from pathlib import Path


HTML_PATH = Path(__file__).parents[1] / "photos_sync" / "web" / "static" / "index.html"


def test_overview_is_the_default_library_section() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'data-s="overview" class="on"' in html
    assert 'onclick="tab(\'overview\',this)"' in html
    assert '<b id="bc-section">Overview</b>' in html
    assert 'data-s="gallery" class="on"' not in html


def test_overview_exposes_library_exif_and_connection_summaries() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    for element_id in (
        "overview-photos",
        "overview-albums",
        "overview-storage",
        "overview-exif-percent",
        "overview-exif-with",
        "overview-exif-pending",
        "overview-exif-without",
        "overview-webdav-state",
        "overview-ssh-state",
        "overview-pipeline-state",
        "overview-recent-days",
    ):
        assert f'id="{element_id}"' in html


def test_overview_loads_existing_api_contracts() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "function loadOverview()" in html
    assert "api('/api/days')" in html
    assert "api('/api/albums')" in html
    assert "api('/api/exif?offset=0&limit=1&status=all')" in html
    assert "api('/api/webdav')" in html
    assert "api('/api/ssh')" in html
    assert "api('/api/pipeline/estado')" in html
    assert "Administrator access required" in html


def test_dashboard_uses_the_sage_and_forest_palette() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "--bg:       #f5f7f4" in html
    assert "--surface:  #ffffff" in html
    assert "--b:        #245c43" in html
    assert "--b2:       #347455" in html
    assert "--b3:       #7faa91" in html
    assert "--ink:      #18231d" in html
