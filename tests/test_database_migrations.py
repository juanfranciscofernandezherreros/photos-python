from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from photos_sync import db
from photos_sync.database_migrations import upgrade_database


def test_fresh_database_upgrades_to_head(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    upgrade_database(engine)

    inspector = inspect(engine)
    assert {"captures", "users", "trash", "photo_exif", "alembic_version"} <= set(inspector.get_table_names())
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0004_photo_exif"


def test_existing_unversioned_database_is_adopted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    db.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE captures ADD COLUMN city TEXT"))

    upgrade_database(engine)

    assert "city" not in {column["name"] for column in inspect(engine).get_columns("captures")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0004_photo_exif"
