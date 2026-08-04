"""
Step 4 of the pipeline: reads captures from the database, groups by day
(year/month/day of capture_date) and stores a
DaySummary per day, sorted from most to fewest photos.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .. import repository as repo
from ..models import Capture, DaySummary
from ..utils.dates import parse_date


def load_captures() -> list[Capture]:
    raw = repo.load_captures()
    if not isinstance(raw, list):
        return []
    return [Capture.from_dict(d) for d in raw]


def group_by_day(captures: list[Capture]) -> list[DaySummary]:
    groups: dict[str, list[Capture]] = defaultdict(list)

    for cap in captures:
        if not cap.capture_date:
            continue
        try:
            date = parse_date(cap.capture_date)
        except ValueError:
            continue
        groups[date.strftime('%Y-%m-%d')].append(cap)

    summaries: list[DaySummary] = []

    for date_str, day_captures in groups.items():
        year, month, day = date_str.split('-')

        dest_folders = {Path(c.dest_path).parent for c in day_captures if c.dest_path}
        dest_folder = str(next(iter(dest_folders))) if dest_folders else None

        zip_paths = {c.zip_path for c in day_captures if c.zip_path}
        zip_path = next(iter(zip_paths)) if zip_paths else None

        summaries.append(DaySummary(
            date=date_str,
            year=year,
            month=month,
            day=day,
            photo_count=len(day_captures),
            total_mb=round(sum(c.size_mb for c in day_captures), 2),
            dest_folder=dest_folder,
            zip_path=zip_path,
            capture_ids=[c.id for c in day_captures],
            filenames=[c.filename for c in day_captures],
        ))

    summaries.sort(key=lambda s: s.photo_count, reverse=True)
    return summaries


def generate_daily_summary() -> None:
    print("Reading captures from database...\n")

    captures = load_captures()
    if not captures:
        print("❌ No captures found. Run the download step first.")
        return

    summaries = group_by_day(captures)

    repo.upsert_summaries([s.to_dict() for s in summaries])

    print("-" * 50)
    print("SUMMARY BY DAY (most -> least photos):")
    for s in summaries:
        print(f"  📅 {s.date}  ->  {s.photo_count} photos ({s.total_mb} MB)")

    total = sum(s.photo_count for s in summaries)
    print("-" * 50)
    print(f"✅ Day summaries saved with {len(summaries)} days "
          f"and {total} photos in total.")


if __name__ == "__main__":
    generate_daily_summary()
