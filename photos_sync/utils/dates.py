"""Centralized date format constant and helpers."""
from __future__ import annotations

from datetime import datetime

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_date(s: str) -> datetime:
    """Parse a capture date string into a datetime object."""
    return datetime.strptime(s, DATE_FORMAT)


def format_date(dt: datetime) -> str:
    """Format a datetime into the standard capture date string."""
    return dt.strftime(DATE_FORMAT)
