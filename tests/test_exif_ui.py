from __future__ import annotations

from pathlib import Path

UI = Path(__file__).parents[1] / "photos_sync/web/static/index.html"


def test_exif_tab_exposes_search_filters_and_details() -> None:
    html = UI.read_text(encoding="utf-8")

    assert 'data-s="exif"' in html
    assert 'id="exif-search"' in html
    assert 'id="exif-status"' in html
    assert 'id="exif-table-body"' in html
    assert "openExif" in html
    assert "/api/exif" in html


def test_exif_extraction_runs_through_background_pipeline() -> None:
    html = UI.read_text(encoding="utf-8")

    assert 'id="btn-exif-run"' in html
    assert "runExifExtraction" in html
    assert "/api/pipeline/ejecutar" in html
    assert "EXIF pipeline step" in html
