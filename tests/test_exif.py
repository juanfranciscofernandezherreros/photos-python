from __future__ import annotations

from pathlib import Path

from PIL import Image
from PIL.TiffImagePlugin import IFDRational
from sqlalchemy import inspect


def _capture(path: Path, capture_id: str = "cap_exif") -> dict:
    return {
        "id": capture_id,
        "archivo": path.name,
        "formato": path.suffix.lstrip("."),
        "tamano_mb": round(path.stat().st_size / 1_048_576, 2),
        "mtime": path.stat().st_mtime,
        "fecha_captura": "",
        "ruta_original": str(path),
        "ruta_destino": str(path),
    }


def _exif_jpeg(path: Path) -> None:
    exif = Image.Exif()
    exif[271] = "Example Camera Corp"
    exif[272] = "Model Pro"
    exif[305] = "Photos Sync Test"
    exif[274] = 1
    exif[36867] = "2024:07:08 09:10:11"
    exif[33434] = IFDRational(1, 125)
    exif[33437] = IFDRational(28, 10)
    exif[34855] = 200
    exif[37386] = IFDRational(50, 1)
    Image.new("RGB", (80, 60), "navy").save(path, exif=exif)


def test_extracts_normalized_and_raw_exif(tmp_path):
    from photos_sync.exif import extract_photo_exif

    path = tmp_path / "portrait.jpg"
    _exif_jpeg(path)

    result = extract_photo_exif(path)

    assert result["has_exif"] is True
    assert (result["width"], result["height"]) == (80, 60)
    assert result["camera_make"] == "Example Camera Corp"
    assert result["camera_model"] == "Model Pro"
    assert result["date_time_original"] == "2024:07:08 09:10:11"
    assert result["exposure_time"] == "1/125"
    assert result["f_number"] == 2.8
    assert result["iso_speed"] == 200
    assert result["focal_length_mm"] == 50.0
    assert result["raw"]["Make"] == "Example Camera Corp"
    assert result["error"] is None


def test_image_without_exif_still_stores_dimensions(tmp_path):
    from photos_sync.exif import extract_photo_exif

    path = tmp_path / "plain.png"
    Image.new("RGB", (32, 24), "white").save(path)

    result = extract_photo_exif(path)

    assert result["has_exif"] is False
    assert (result["width"], result["height"]) == (32, 24)
    assert result["raw"] == {}
    assert result["error"] is None


def test_missing_photo_records_extraction_error(tmp_path):
    from photos_sync.exif import extract_photo_exif

    result = extract_photo_exif(tmp_path / "missing.jpg")

    assert result["has_exif"] is False
    assert result["error"] == "File not found"


def test_repository_pages_filters_and_updates_exif(tmp_path, db_engine):
    from photos_sync import repository as repo
    from photos_sync.exif import extract_photo_exif

    with_exif = tmp_path / "camera.jpg"
    without_exif = tmp_path / "screenshot.png"
    pending = tmp_path / "pending.png"
    _exif_jpeg(with_exif)
    Image.new("RGB", (20, 10), "white").save(without_exif)
    Image.new("RGB", (10, 20), "black").save(pending)
    repo.upsert_captures([
        _capture(with_exif, "cap_camera"),
        _capture(without_exif, "cap_screen"),
        _capture(pending, "cap_pending"),
    ])
    camera_record = extract_photo_exif(with_exif)
    camera_record["capture_id"] = "cap_camera"
    screen_record = extract_photo_exif(without_exif)
    screen_record["capture_id"] = "cap_screen"
    repo.upsert_photo_exif([camera_record, screen_record])

    records, total, stats = repo.load_photo_exif_page(0, 20)

    assert total == 3
    assert len(records) == 3
    assert stats == {
        "total": 3,
        "extracted": 2,
        "with_exif": 1,
        "without_exif": 1,
        "errors": 0,
        "pending": 1,
    }
    filtered, filtered_total, _ = repo.load_photo_exif_page(
        0, 20, "Model Pro", "with_exif"
    )
    assert filtered_total == 1
    assert filtered[0]["capture_id"] == "cap_camera"
    detail = repo.get_photo_exif("cap_camera")
    assert detail is not None
    assert detail["raw"]["Model"] == "Model Pro"

    camera_record["camera_model"] = "Model Pro II"
    repo.upsert_photo_exif([camera_record])
    assert repo.get_photo_exif("cap_camera")["camera_model"] == "Model Pro II"


def test_classification_persists_exif_and_original_date(tmp_path):
    from photos_sync import repository as repo
    from photos_sync.pipeline.classify import classify_captures

    path = tmp_path / "ordinary.jpg"
    _exif_jpeg(path)
    repo.upsert_captures([_capture(path)])

    classify_captures()

    detail = repo.get_photo_exif("cap_exif")
    capture = repo.load_captures()[0]
    assert detail is not None
    assert detail["camera_model"] == "Model Pro"
    assert capture["fecha_captura"] == "2024-07-08T09:10:11"
    assert "camera" in capture["tags"]


def test_classification_reuses_unchanged_exif(tmp_path, monkeypatch):
    from photos_sync import repository as repo
    from photos_sync.pipeline import classify as classify_module

    path = tmp_path / "unchanged.jpg"
    _exif_jpeg(path)
    repo.upsert_captures([_capture(path, "cap_unchanged")])
    classify_module.classify_captures()

    def unexpected_read(_path):
        raise AssertionError("Unchanged photo was read from disk again")

    monkeypatch.setattr(classify_module, "extract_photo_exif", unexpected_read)
    classify_module.classify_captures()

    assert repo.get_photo_exif("cap_unchanged")["camera_model"] == "Model Pro"


def test_exif_schema_has_one_to_one_table_and_indexes(db_engine):
    inspector = inspect(db_engine)
    columns = {column["name"] for column in inspector.get_columns("photo_exif")}
    indexes = {index["name"] for index in inspector.get_indexes("photo_exif")}

    assert {"capture_id", "camera_model", "date_time_original", "raw_json", "error"} <= columns
    assert {"ix_photo_exif_extracted_at", "ix_photo_exif_camera"} <= indexes


def test_exif_api_lists_and_returns_details(cliente_api, tmp_path):
    from photos_sync import repository as repo
    from photos_sync.exif import extract_photo_exif

    path = tmp_path / "api-camera.jpg"
    _exif_jpeg(path)
    repo.upsert_captures([_capture(path, "cap_api")])
    record = extract_photo_exif(path)
    record["capture_id"] = "cap_api"
    repo.upsert_photo_exif([record])

    page = cliente_api.get("/api/exif?status=with_exif").json()
    detail = cliente_api.get("/api/exif/cap_api")

    assert page["count"] == 1
    assert page["records"][0]["camera_model"] == "Model Pro"
    assert page["records"][0]["thumbnail_url"].startswith("/api/thumb?path=")
    assert detail.status_code == 200
    assert detail.json()["raw"]["Make"] == "Example Camera Corp"


def test_exif_api_requires_login(cliente_anon):
    assert cliente_anon.get("/api/exif").status_code == 401
    assert cliente_anon.get("/api/exif/missing").status_code == 401


def test_exif_detail_returns_404_for_unknown_capture(cliente_api):
    assert cliente_api.get("/api/exif/missing").status_code == 404
