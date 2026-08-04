"""
ejecutar_todo.py — Run the full Photos Sync pipeline.

Executes the same 5 steps as the web interface, in order and headless:
  1. Download metadata
  2. Organize by date
  3. Compress by day
  4. Generate summary
  5. Upload to SSH

Usage:
    python -m photos_sync.ejecutar_todo
"""
from __future__ import annotations

from photos_sync.pipeline.compress import compress_folders_by_day
from photos_sync.pipeline.download import sync_captures
from photos_sync.pipeline.organize import organize_captures_by_date
from photos_sync.pipeline.summary import generate_daily_summary
from photos_sync.pipeline.upload_ssh import upload_organized_to_ssh

PASOS = [
    ("Sync & save captures", sync_captures),
    ("Organize by date",    organize_captures_by_date),
    ("Compress by day",     compress_folders_by_day),
    ("Generate summary",    generate_daily_summary),
    ("Upload to SSH",       upload_organized_to_ssh),
]


def main():
    print("\n--- Photos Sync: starting full pipeline ---\n")
    for nombre, fn in PASOS:
        print(f"{'=' * 55}")
        print(f"⏳ {nombre}")
        print(f"{'=' * 55}\n")
        fn()
        print()
    print("--- Pipeline finished ---")


if __name__ == "__main__":
    main()
