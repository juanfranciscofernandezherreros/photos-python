"""Centralized date format constant and helpers."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_date(s: str) -> datetime:
    """Parse a capture date string into a datetime object."""
    return datetime.strptime(s, DATE_FORMAT)


def format_date(dt: datetime) -> str:
    """Format a datetime into the standard capture date string."""
    return dt.strftime(DATE_FORMAT)


# Common phone/camera filename patterns → date extraction
_DATE_PATTERNS = [
    # Android screenshots: Screenshot_20250629-133659.png
    re.compile(r"(\d{4})(\d{2})(\d{2})[-_](\d{2})(\d{2})(\d{2})"),
    # Camera photos: IMG_20250629_133659.jpg / VID_20250629_133659.mp4
    re.compile(r"[A-Za-z]+_(\d{4})(\d{2})(\d{2})[-_](\d{2})(\d{2})(\d{2})"),
    # MIUI / Xiaomi screenshots with dashes and optional ms:
    # Screenshot_2023-11-25-16-43-36-993_com.bbva.jpg
    # Screenshot_2023-11-25-16-43-36.jpg
    re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})"),
    # iPhone / bare ISO in name: 2025-06-29 13.36.59.jpg
    re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _](\d{2})[.\-:](\d{2})[.\-:](\d{2})"),
    # Fallback: just a date, no time (Screenshot_20250629.png)
    re.compile(r"(\d{4})(\d{2})(\d{2})"),
]


def extract_date_from_filename(name: str) -> str:
    """Extract an ISO date (YYYY-MM-DDTHH:MM:SS) from a filename.

    Returns "" if no recognisable date is found. Handles common Android /
    iOS / camera patterns:
      Screenshot_20250629-133659.png  → 2025-06-29T13:36:59
      IMG_20250629_133659.jpg         → 2025-06-29T13:36:59
      2025-06-29 13.36.59.jpg         → 2025-06-29T13:36:59
    """
    if not name:
        return ""
    base = Path(name).stem  # strip extension

    for pat in _DATE_PATTERNS:
        m = pat.search(base)
        if not m:
            continue
        try:
            groups = m.groups()
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            # Sanity range check
            if not (1970 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31):
                continue
            if len(groups) >= 6:
                hh, mm, ss = int(groups[3]), int(groups[4]), int(groups[5])
                if not (0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60):
                    hh = mm = ss = 0
                dt = datetime(year, month, day, hh, mm, ss)
            else:
                dt = datetime(year, month, day)
            return dt.isoformat(timespec="seconds")
        except (ValueError, IndexError):
            continue
    return ""
