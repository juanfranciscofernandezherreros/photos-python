"""Exercise schema migrations, types, and constraints on disposable PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from photos_sync.db import get_engine, init_db, t_album_photos, t_captures
from photos_sync.runtime_secrets import get_database_url

EXPECTED_INDEXES = {
    "ix_captures_dest_path",
    "ix_captures_source_path",
    "ix_captures_capture_day",
    "ix_captures_favourite_day",
}


def main() -> None:
    url = make_url(get_database_url())
    if url.get_backend_name() != "postgresql" or not (url.database or "").startswith("photos_sync_ci"):
        raise SystemExit("Refusing to run PostgreSQL integration checks outside photos_sync_ci*")

    engine = get_engine()
    init_db(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"alembic_version", "captures", "albums", "album_photos", "users"} <= tables
    assert EXPECTED_INDEXES <= {item["name"] for item in inspector.get_indexes("captures")}

    probe_id = f"ci-{uuid.uuid4()}"
    with engine.begin() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == "0003_drop_city"
        connection.execute(
            t_captures.insert().values(
                id=probe_id,
                filename="ci-probe.jpg",
                extension="jpg",
                size_mb=1.0,
                mtime=1.0,
                capture_date=datetime(2026, 8, 5, 12, 30),
                capture_day=date(2026, 8, 5),
                source_path=f"ci://{probe_id}",
            )
        )
        stored = connection.execute(
            select(t_captures.c.capture_date, t_captures.c.capture_day).where(
                t_captures.c.id == probe_id
            )
        ).one()
        assert isinstance(stored.capture_date, datetime)
        assert stored.capture_day == date(2026, 8, 5)

    duplicate_blocked = False
    try:
        with engine.begin() as connection:
            connection.execute(
                t_album_photos.insert(),
                [
                    {"album_id": "ci-album", "photo_path": "ci-photo"},
                    {"album_id": "ci-album", "photo_path": "ci-photo"},
                ],
            )
    except IntegrityError:
        duplicate_blocked = True
    assert duplicate_blocked, "PostgreSQL did not enforce the album/photo unique index"

    with engine.begin() as connection:
        connection.execute(t_album_photos.delete().where(t_album_photos.c.album_id == "ci-album"))
        connection.execute(t_captures.delete().where(t_captures.c.id == probe_id))

    print(f"PostgreSQL integration verified at Alembic revision {revision}")


if __name__ == "__main__":
    main()
