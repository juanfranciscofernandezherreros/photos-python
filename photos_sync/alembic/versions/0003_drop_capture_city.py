"""Remove the obsolete capture city column."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_drop_city"
down_revision = "0002_capture_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("captures")}
    if "city" in columns:
        op.drop_column("captures", "city")


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("captures")}
    if "city" not in columns:
        op.add_column("captures", sa.Column("city", sa.Text(), nullable=True))
