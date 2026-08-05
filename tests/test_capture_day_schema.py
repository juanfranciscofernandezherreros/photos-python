from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import inspect, select


def test_upsert_stores_native_capture_timestamp_and_indexed_day(db_engine):
    from photos_sync import repository as repo
    from photos_sync.db import t_captures

    repo.upsert_captures([{
        "id": "capture-date-types",
        "archivo": "IMG_20240615_123456.jpg",
        "formato": "jpg",
        "tamano_mb": 1.0,
        "mtime": 0,
        "fecha_captura": "",
        "ruta_original": "/source/IMG_20240615_123456.jpg",
    }])

    with db_engine.connect() as connection:
        row = connection.execute(select(t_captures)).mappings().one()

    assert row["capture_date"] == datetime(2024, 6, 15, 12, 34, 56)
    assert row["capture_day"] == date(2024, 6, 15)
    assert repo.load_captures()[0]["fecha_captura"] == "2024-06-15T12:34:56"


def test_capture_day_falls_back_to_mtime(db_engine):
    from photos_sync import repository as repo
    from photos_sync.db import t_captures

    timestamp = datetime(2024, 7, 2, 8, 30).timestamp()
    repo.upsert_captures([{
        "id": "capture-mtime-day",
        "archivo": "photo-without-date.jpg",
        "formato": "jpg",
        "tamano_mb": 1.0,
        "mtime": timestamp,
        "fecha_captura": "",
        "ruta_original": "/source/photo-without-date.jpg",
    }])

    with db_engine.connect() as connection:
        capture_day = connection.execute(select(t_captures.c.capture_day)).scalar_one()

    assert capture_day == date(2024, 7, 2)


def test_zero_mtime_remains_undated(db_engine):
    from photos_sync import repository as repo
    from photos_sync.db import t_captures

    repo.upsert_captures([{
        "id": "capture-undated",
        "archivo": "photo-without-date.jpg",
        "formato": "jpg",
        "tamano_mb": 1.0,
        "mtime": 0,
        "fecha_captura": "",
        "ruta_original": "/source/photo-without-date.jpg",
    }])

    with db_engine.connect() as connection:
        capture_day = connection.execute(select(t_captures.c.capture_day)).scalar_one()

    assert capture_day is None


def test_performance_indexes_are_created(db_engine):
    indexes = {
        index["name"]
        for table in ("captures", "album_photos", "trash")
        for index in inspect(db_engine).get_indexes(table)
    }

    assert {
        "ix_captures_dest_path",
        "ix_captures_source_path",
        "ix_captures_capture_day",
        "ix_captures_favourite_day",
        "ux_album_photos_album_path",
        "ix_album_photos_photo_path",
        "ix_trash_deleted_at",
    } <= indexes
