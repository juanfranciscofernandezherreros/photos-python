"""UI contracts for daily ZIP downloads."""
from pathlib import Path


HTML_PATH = Path(__file__).parents[1] / "photos_sync" / "web" / "static" / "index.html"


def test_gallery_offers_all_and_single_day_zip_downloads() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'id="download-all-days"' in html
    assert "Download all days" in html
    assert "function downloadDays(dates,button)" in html
    assert "/api/days/download-zip?dates=" in html
    assert "downloadDays([d.fecha],downloadButton)" in html
    assert 'aria-label="Download this day as a ZIP archive"' in html


def test_gallery_does_not_render_the_removed_daily_chart() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "Photos by day" not in html
    assert 'id="day-photo-chart"' not in html
    assert "function renderDayChart(days)" not in html
