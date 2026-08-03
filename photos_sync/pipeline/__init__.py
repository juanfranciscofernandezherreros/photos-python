"""Pipeline package — database-backed sync steps + orchestration."""
from __future__ import annotations

from .download import sync_captures
from .organize import organize_captures_by_date
from .classify import classify_captures
from .compress import compress_folders_by_day
from .summary import generate_daily_summary
from .upload_ssh import upload_organized_to_ssh
