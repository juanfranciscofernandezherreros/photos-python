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


def test_exif_detail_shows_the_complete_photo_in_a_responsive_modal() -> None:
    html = UI.read_text(encoding="utf-8")

    assert 'id="modal-card"' in html
    assert ".modal-card.exif-detail-modal{width:min(920px,calc(100vw - 48px))}" in html
    assert ".exif-preview img{width:100%;height:100%;display:block;object-fit:contain}" in html
    assert "const previewUrl=record.photo_url||record.thumbnail_url||''" in html
    assert ".exif-detail-grid{grid-template-columns:1fr}" in html
    assert ".exif-raw-row{grid-template-columns:1fr;gap:4px}" in html
    assert "max-height:calc(100dvh - 24px)" in html
    assert ".exif-raw{margin-top:12px;border:1px solid var(--brd)" in html
