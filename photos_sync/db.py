"""
db.py — SQLAlchemy engine + all table definitions.

One engine is created per process (singleton).  Tests inject a
SQLite in-memory engine via ``set_engine()``.  Production defaults
to the DATABASE_URL environment variable (PostgreSQL).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, Float, Integer, MetaData, Table, Text,
    create_engine,
)
from sqlalchemy.pool import StaticPool

# ── Singleton engine ──────────────────────────────────────────────────────────

_ENGINE = None


def get_engine():
    """Return the process-wide SQLAlchemy engine, creating it on first call."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = _create_engine_from_url(
            os.environ.get(
                "DATABASE_URL",
                "postgresql://localhost/photos_sync",
            )
        )
    return _ENGINE


def set_engine(engine) -> None:
    """Override the engine — used by tests to inject SQLite in-memory."""
    global _ENGINE
    _ENGINE = engine


def _create_engine_from_url(url: str):
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url, pool_pre_ping=True)


# ── Schema ────────────────────────────────────────────────────────────────────

metadata = MetaData()

# SSH connections (alias is PK)
t_ssh = Table(
    "ssh_connections", metadata,
    Column("alias",             Text, primary_key=True),
    Column("host",              Text, nullable=False),
    Column("port",              Integer, nullable=False, default=22),
    Column("username",          Text, nullable=False),
    Column("remote_path",       Text, nullable=False, default=""),
    Column("remote_path_dest",  Text, nullable=False, default=""),
    Column("private_key_path",  Text, nullable=False, default=""),
    Column("role",              Text, nullable=False, default="origen"),
)

# WebDAV connections (drive letter is PK)
t_webdav = Table(
    "webdav_connections", metadata,
    Column("drive_letter", Text, primary_key=True),
    Column("ip",           Text, nullable=False),
    Column("port",         Text, nullable=False, default="8080"),
    Column("alias",        Text, nullable=False, default=""),
)

# Source folders (path is PK)
t_folders = Table(
    "source_folders", metadata,
    Column("path", Text, primary_key=True),
)

# Destination config — single row (id always = 1, upserted)
t_destination = Table(
    "destination_config", metadata,
    Column("id",        Integer, primary_key=True, default=1),
    Column("type",      Text, nullable=False, default="local"),  # 'local'|'ssh'
    Column("path",      Text),       # set when type='local'
    Column("ssh_alias", Text),       # set when type='ssh'
)

# Photo captures / metadata
t_captures = Table(
    "captures", metadata,
    Column("id",               Text, primary_key=True),
    Column("filename",         Text, nullable=False),
    Column("extension",        Text, nullable=False, default=""),
    Column("size_mb",          Float, nullable=False, default=0.0),
    Column("mtime",            Float, nullable=False, default=0.0),
    Column("capture_date",     Text, nullable=False, default=""),
    Column("source_path",      Text, nullable=False, default=""),
    Column("dest_path",        Text),
    Column("zip_path",         Text),
    Column("ssh_alias",        Text),
    Column("ssh_remote_path",  Text),
    Column("gps_lat",          Float),
    Column("gps_lon",          Float),
    Column("city",             Text),
    # Tags stored as JSON string, e.g. '["camera","has_gps"]'
    Column("tags",             Text, nullable=False, default="[]"),
    Column("is_favourite",     Boolean, nullable=False, default=False),
)

# Day summaries
t_summaries = Table(
    "day_summaries", metadata,
    Column("date",        Text, primary_key=True),  # 'YYYY-MM-DD'
    Column("year",        Text),
    Column("month",       Text),
    Column("day",         Text),
    Column("photo_count", Integer, default=0),
    Column("total_mb",    Float, default=0.0),
    Column("dest_folder", Text),
    Column("zip_path",    Text),
)

# Albums
t_albums = Table(
    "albums", metadata,
    Column("id",         Text, primary_key=True),
    Column("name",       Text, nullable=False),
    Column("cover",      Text),
    Column("created_at", Text, nullable=False),
)

# Album ↔ photo junction (many-to-many)
t_album_photos = Table(
    "album_photos", metadata,
    Column("album_id",   Text, nullable=False),
    Column("photo_path", Text, nullable=False),
)

# Users — authentication and roles
t_users = Table(
    "users", metadata,
    Column("id",            Text, primary_key=True),
    Column("username",      Text, nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role",          Text, nullable=False, default="user"),  # 'admin' | 'user'
    Column("created_at",    Text, nullable=False),
    Column("active",        Boolean, nullable=False, default=True),
)

# Trash — deleted photos pending permanent removal or restore
t_trash = Table(
    "trash", metadata,
    Column("id",            Text, primary_key=True),   # uuid
    Column("original_path", Text, nullable=False),      # where it was before delete
    Column("trash_path",    Text, nullable=False),      # where it lives now (.trash/…)
    Column("filename",      Text, nullable=False),
    Column("size_mb",       Float, nullable=False, default=0.0),
    Column("deleted_at",    Text, nullable=False),       # ISO timestamp
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def init_db(engine=None) -> None:
    """Create all tables if they don't exist yet, plus the single-admin guard."""
    eng = engine or get_engine()
    metadata.create_all(eng)
    _ensure_single_admin_index(eng)


def _ensure_single_admin_index(eng) -> None:
    """Enforce 'at most one admin' at the database level.

    A partial unique index guarantees the DB rejects a second admin row
    even if the application-level check is bypassed or hits a race
    condition. Works on both PostgreSQL and SQLite (both support partial
    indexes via this syntax).
    """
    from sqlalchemy import text as _sql_text
    stmt = (
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_admin "
        "ON users (role) WHERE role = 'admin'"
    )
    try:
        with eng.begin() as conn:
            conn.execute(_sql_text(stmt))
    except Exception:
        # Some very old SQLite builds lack partial-index support; the
        # application-level check in repository.create_user still applies.
        pass


def encode_tags(tags: list) -> str:
    return json.dumps(tags or [])


def decode_tags(raw: str | None) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []
