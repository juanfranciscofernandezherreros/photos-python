"""Pipeline package — database-backed sync steps + orchestration."""
from __future__ import annotations

from .classify import classify_captures as classify_captures
from .compress import compress_folders_by_day as compress_folders_by_day
from .download import sync_captures as sync_captures
from .organize import organize_captures_by_date as organize_captures_by_date
from .summary import generate_daily_summary as generate_daily_summary
from .upload_ssh import upload_organized_to_ssh as upload_organized_to_ssh
