from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from rich.progress import track

from .. import repository as repo
from ..config import ORGANIZED_DIR, ZIPS_DIR
from ..models import Capture
from ..storage.folders import load_saved_destination

DELETE_ORIGINALS_AFTER_COMPRESS: bool = False  # set True to remove day folders after zipping


def zip_is_valid(zip_path: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def compress_folders_by_day() -> None:
    dest_str = load_saved_destination()
    if dest_str:
        base_folder = Path(dest_str)
        zips_folder = base_folder / "Comprimidos"
    else:
        base_folder = ORGANIZED_DIR
        zips_folder = ZIPS_DIR

    if not base_folder.exists():
        print(f"❌ Error: Folder '{base_folder}' does not exist.")
        return

    zips_folder.mkdir(parents=True, exist_ok=True)

    # Load existing metadata to update zip_path fields
    raw = repo.load_captures()
    captures: list[Capture] = []
    if isinstance(raw, list):
        captures = [Capture.from_dict(d) for d in raw]

    print(f"Searching for day folders in: {base_folder.resolve()}...\n")
    if DELETE_ORIGINALS_AFTER_COMPRESS:
        print("⚠️ DELETE_ORIGINALS_AFTER_COMPRESS is enabled: day folders will be\n"
              "   deleted once their .zip file is verified as valid.\n")
    print("-" * 50)

    zips_created = 0
    errors = 0
    deleted_folders = 0

    day_folders: list[Path] = [
        day
        for year in base_folder.iterdir() if year.is_dir() and year.name != "Comprimidos"
        for month in year.iterdir() if month.is_dir()
        for day in month.iterdir() if day.is_dir()
    ]

    for day_folder in track(day_folders, description="Compressing by day..."):
        year = day_folder.parent.parent.name
        month = day_folder.parent.name
        day = day_folder.name

        zip_path = zips_folder / f"Capturas_{year}-{month}-{day}.zip"

        if zip_path.exists() and zip_is_valid(zip_path):
            # Update metadata in case zip_path wasn't recorded yet
            for cap in captures:
                if cap.dest_path and Path(cap.dest_path).parent == day_folder:
                    cap.zip_path = str(zip_path)
            continue

        files = [f for f in day_folder.rglob('*') if f.is_file()]
        if not files:
            continue

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file in files:
                    zf.write(file, file.relative_to(day_folder))

            if zip_is_valid(zip_path):
                print(f"📦 Compressed: {year}\\{month}\\{day} -> {zip_path.name}")
                for cap in captures:
                    if cap.dest_path and Path(cap.dest_path).parent == day_folder:
                        cap.zip_path = str(zip_path)
                zips_created += 1

                if DELETE_ORIGINALS_AFTER_COMPRESS:
                    shutil.rmtree(day_folder)
                    deleted_folders += 1
            else:
                zip_path.unlink(missing_ok=True)
                print(f"⚠️ ZIP validation failed for {day_folder}, skipping.")
                errors += 1

        except Exception as e:
            print(f"⚠️ Could not compress '{day_folder}': {e}")
            errors += 1

    if captures:
        repo.upsert_captures([c.to_dict() for c in captures])

    print("-" * 50)
    print("COMPRESSION SUMMARY:")
    print(f"  - New ZIP files created: {zips_created}")
    if errors:
        print(f"  - Errors: {errors}")
    if deleted_folders:
        print(f"  - Day folders deleted: {deleted_folders}")
    print(f"\n📁 Your compressed files are ready in: {zips_folder.resolve()}")


if __name__ == "__main__":
    compress_folders_by_day()
