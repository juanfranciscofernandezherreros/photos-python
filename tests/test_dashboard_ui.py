"""Contract tests for the overview dashboard."""

from pathlib import Path


HTML_PATH = Path(__file__).parents[1] / "photos_sync" / "web" / "static" / "index.html"


def test_overview_is_the_default_library_section() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'data-s="overview" class="on"' in html
    assert 'onclick="tab(\'overview\',this)"' in html
    assert '<b id="bc-section">Home</b>' in html
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


def test_navigation_uses_plain_language_labels() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    for label in (
        "Home",
        "All photos",
        "Photo information",
        "Organize &amp; backup",
        "Add from phone",
        "Settings",
        "Recycle bin",
    ):
        assert label in html


def test_settings_offer_task_based_guided_choices() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'data-s="settings"' in html
    assert "You do not need to configure everything" in html
    assert "Phone import" in html
    assert "Storage locations" in html
    assert "Remote storage" in html
    assert "People and access" in html
    assert "Advanced connection options" in html
    assert "Back to settings" in html


def test_home_includes_a_three_step_getting_started_guide() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "Start here" in html
    assert "Connect your phone" in html
    assert "Copy your photos" in html
    assert "Organize and protect" in html
