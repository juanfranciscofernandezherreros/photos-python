"""Normalize capture dates and add gallery indexes."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_capture_dates"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_captures_dest_path ON captures (dest_path) "
    "WHERE dest_path IS NOT NULL AND dest_path <> ''",
    "CREATE INDEX IF NOT EXISTS ix_captures_source_path ON captures (source_path)",
    "CREATE INDEX IF NOT EXISTS ix_captures_capture_day ON captures (capture_day DESC)",
    "CREATE INDEX IF NOT EXISTS ix_captures_favourite_day "
    "ON captures (is_favourite, capture_day DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_album_photos_album_path "
    "ON album_photos (album_id, photo_path)",
    "CREATE INDEX IF NOT EXISTS ix_album_photos_photo_path ON album_photos (photo_path)",
    "CREATE INDEX IF NOT EXISTS ix_trash_deleted_at ON trash (deleted_at)",
)


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"]: column for column in inspect(connection).get_columns("captures")}
    if "capture_day" not in columns:
        op.add_column("captures", sa.Column("capture_day", sa.Date(), nullable=True))

    if connection.dialect.name == "postgresql":
        op.execute("""
            UPDATE captures
            SET capture_day = CASE
                WHEN capture_date IS NOT NULL AND btrim(capture_date::text) <> ''
                     AND pg_input_is_valid(btrim(capture_date::text), 'timestamp without time zone')
                    THEN btrim(capture_date::text)::timestamp::date
                WHEN mtime > 0 THEN to_timestamp(mtime)::date
                ELSE NULL
            END
            WHERE capture_day IS NULL
        """)
        capture_column = columns.get("capture_date")
        capture_type = str(capture_column["type"] if capture_column else "").lower()
        if "char" in capture_type or "text" in capture_type:
            op.alter_column(
                "captures",
                "capture_date",
                existing_type=columns["capture_date"]["type"],
                type_=sa.DateTime(),
                nullable=True,
                postgresql_using=(
                    "CASE WHEN capture_date IS NOT NULL AND btrim(capture_date) <> '' "
                    "AND pg_input_is_valid(btrim(capture_date), 'timestamp without time zone') "
                    "THEN btrim(capture_date)::timestamp ELSE NULL END"
                ),
            )

    for statement in INDEXES:
        op.execute(statement)


def downgrade() -> None:
    for name in (
        "ix_trash_deleted_at",
        "ix_album_photos_photo_path",
        "ux_album_photos_album_path",
        "ix_captures_favourite_day",
        "ix_captures_capture_day",
        "ix_captures_source_path",
        "ix_captures_dest_path",
    ):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    if "capture_day" in {c["name"] for c in inspect(op.get_bind()).get_columns("captures")}:
        op.drop_column("captures", "capture_day")
