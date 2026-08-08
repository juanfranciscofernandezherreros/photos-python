"""UI contracts for the simplified day and album gallery panel."""

from pathlib import Path


HTML_PATH = Path(__file__).parents[1] / "photos_sync" / "web" / "static" / "index.html"


def test_day_gallery_prioritizes_browsing_over_actions() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'id="gp-select-button"' in html
    assert "Select photos" in html
    assert 'id="gp-tags-toggle"' in html
    assert 'aria-expanded="false"' in html
    assert "#gallery-panel.day-view .gp-photo-alb" in html
    assert "#gallery-panel.day-view .gp-photo-del" in html


def test_gallery_selection_is_an_explicit_mode() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "function toggleGallerySelection()" in html
    assert "_gallerySelectionRequested=true" in html
    assert "classList.add('selection-mode')" in html
    assert "Done selecting" in html
    assert "`Done (${count})`" in html


def test_gallery_photos_have_dark_hover_and_black_selected_states() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert ".gp-photo:hover::after{background:rgba(0,0,0,.18)}" in html
    assert ".gp-photo.selected::after{background:rgba(0,0,0,.48)}" in html
    assert ".gp-photo.selected{outline:3px solid #111" in html
    assert ".gp-photo.selected .sel-check{background:#111;border-color:#fff}" in html


def test_gallery_photos_use_a_responsive_grid_without_overlap() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px" in html
    assert ".gp-grid{grid-template-columns:repeat(2,minmax(0,1fr))}" in html
    assert ".gp-grid{grid-template-columns:1fr;gap:8px}" in html
    assert "width:100%;min-width:0" in html
    assert "aspect-ratio:4/3" in html
    assert "object-fit:cover" in html
    assert "left:var(--sb-w);width:auto" in html
    assert "max-width:1320px" in html
    assert "GP_THUMB_SIZE=480" in html


def test_day_gallery_has_clear_navigation_and_download_action() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert 'class="gph-close" type="button"' in html
    assert "Download day" in html
    assert "function downloadCurrentDay(button)" in html
    assert "day.fecha==='undated'?'Undated photos'" in html


def test_day_gallery_matches_the_compact_timeline_style() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "#gallery-panel.day-view .gp-grid{" in html
    assert "grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:6px" in html
    assert "#gallery-panel.day-view .gp-photo{aspect-ratio:1;border-radius:6px}" in html
    assert "repeat(auto-fill,minmax(105px,1fr));gap:5px" in html


def test_gallery_photo_actions_have_accessible_labels() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "favBtn.setAttribute('aria-label',favBtn.title)" in html
    assert "delBtn.setAttribute('aria-label',delBtn.title)" in html
    assert "albBtn.setAttribute('aria-label',albBtn.title)" in html


def test_gallery_tags_are_collapsed_until_requested() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "function toggleGalleryTags()" in html
    assert "function closeGalleryTags()" in html
    assert "toggle.style.display=allTags.length?'inline-flex':'none'" in html


def test_album_photos_open_normally_outside_selection_mode() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    assert "if(_selMode){if(_selThumb(div,p,e))return;}" in html
    assert "if(_gpAlbumId||_selMode)" not in html
