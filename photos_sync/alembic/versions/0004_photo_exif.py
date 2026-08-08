"""Store normalized EXIF metadata for each photo."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0004_photo_exif"
down_revision = "0003_drop_city"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    tables = set(inspect(connection).get_table_names())
    if "photo_exif" not in tables:
        op.create_table(
            "photo_exif",
            sa.Column(
                "capture_id",
                sa.Text(),
                sa.ForeignKey("captures.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("file_path", sa.Text(), nullable=False),
            sa.Column("file_mtime", sa.Float(), nullable=False, server_default="0"),
            sa.Column("extracted_at", sa.DateTime(), nullable=False),
            sa.Column("has_exif", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("width", sa.Integer()),
            sa.Column("height", sa.Integer()),
            sa.Column("camera_make", sa.Text()),
            sa.Column("camera_model", sa.Text()),
            sa.Column("lens_model", sa.Text()),
            sa.Column("software", sa.Text()),
            sa.Column("artist", sa.Text()),
            sa.Column("copyright", sa.Text()),
            sa.Column("date_time_original", sa.Text()),
            sa.Column("offset_time_original", sa.Text()),
            sa.Column("orientation", sa.Integer()),
            sa.Column("exposure_time", sa.Text()),
            sa.Column("f_number", sa.Float()),
            sa.Column("iso_speed", sa.Integer()),
            sa.Column("focal_length_mm", sa.Float()),
            sa.Column("flash", sa.Text()),
            sa.Column("white_balance", sa.Text()),
            sa.Column("metering_mode", sa.Text()),
            sa.Column("exposure_program", sa.Text()),
            sa.Column("gps_lat", sa.Float()),
            sa.Column("gps_lon", sa.Float()),
            sa.Column("gps_altitude_m", sa.Float()),
            sa.Column("raw_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("error", sa.Text()),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_photo_exif_extracted_at "
        "ON photo_exif (extracted_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_photo_exif_camera "
        "ON photo_exif (camera_make, camera_model)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_photo_exif_camera")
    op.execute("DROP INDEX IF EXISTS ix_photo_exif_extracted_at")
    if "photo_exif" in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table("photo_exif")
