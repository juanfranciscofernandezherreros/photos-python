"""Programmatic Alembic entry point used during self-hosted startup."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

BASELINE_REVISION = "0001_initial_schema"


def _config(connection) -> Config:
    package_dir = Path(__file__).resolve().parent
    config = Config(str(package_dir / "alembic.ini"))
    config.set_main_option("script_location", str(package_dir / "alembic"))
    config.attributes["connection"] = connection
    return config


def upgrade_database(engine: Engine) -> None:
    """Upgrade to ``head``, adopting an unversioned legacy database safely."""
    with engine.begin() as connection:
        config = _config(connection)
        tables = set(inspect(connection).get_table_names())
        if tables.intersection({"captures", "users", "albums"}) and "alembic_version" not in tables:
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")
