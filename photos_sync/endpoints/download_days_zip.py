"""Download one or more capture days as a ZIP archive."""
from __future__ import annotations

import re
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .. import repository as repo
from ..auth import require_login
from ..web_server import _is_allowed

router = APIRouter()

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ARCHIVE_CHUNK_SIZE = 1024 * 1024
_MAX_EXPLICIT_DAYS = 366


def _effective_day(capture: dict) -> str:
    capture_date = str(capture.get("fecha_captura") or "").strip()
    if len(capture_date) >= 10:
        candidate = capture_date[:10]
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate
        except ValueError:
            pass

    try:
        return datetime.fromtimestamp(float(capture.get("mtime"))).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return "undated"


def _requested_days(raw_dates: str, available_days: set[str]) -> list[str]:
    if raw_dates.strip().lower() == "all":
        return sorted(available_days, reverse=True)

    days = list(dict.fromkeys(part.strip() for part in raw_dates.split(",") if part.strip()))
    if not days:
        raise HTTPException(400, "Choose at least one day to download")
    if len(days) > _MAX_EXPLICIT_DAYS:
        raise HTTPException(400, f"Choose no more than {_MAX_EXPLICIT_DAYS} days")
    for day in days:
        if day == "undated":
            continue
        if not _DATE_PATTERN.fullmatch(day):
            raise HTTPException(400, "Dates must use the YYYY-MM-DD format")
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as error:
            raise HTTPException(400, "Dates must be valid calendar days") from error
    return days


@router.get("/api/days/download-zip")
def download_days_zip(
    dates: str,
    _auth: dict = Depends(require_login),
):
    """Download photos grouped into one folder per requested capture day."""
    captures = repo.load_captures()
    captures_by_day: dict[str, list[Path]] = {}
    for capture in captures:
        raw_path = capture.get("ruta_destino") or capture.get("ruta_original") or ""
        if raw_path:
            captures_by_day.setdefault(_effective_day(capture), []).append(Path(raw_path))

    requested_days = _requested_days(dates, set(captures_by_day))
    archive_entries: list[tuple[str, Path]] = []
    for day in requested_days:
        seen_names: dict[str, int] = {}
        for photo_path in captures_by_day.get(day, []):
            if not _is_allowed(photo_path) or not photo_path.is_file():
                continue
            name = photo_path.name
            if name in seen_names:
                seen_names[name] += 1
                name = f"{photo_path.stem}_{seen_names[name]}{photo_path.suffix}"
            else:
                seen_names[name] = 1
            archive_entries.append((str(PurePosixPath(day, name)), photo_path))

    if not archive_entries:
        raise HTTPException(404, "No downloadable photos were found for the selected days")

    archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as zip_file:
        for archive_name, photo_path in archive_entries:
            zip_file.write(photo_path, arcname=archive_name)
    archive.seek(0)

    def iter_archive():
        try:
            while chunk := archive.read(_ARCHIVE_CHUNK_SIZE):
                yield chunk
        finally:
            archive.close()

    filename = (
        f"photos_{requested_days[0]}.zip"
        if len(requested_days) == 1
        else f"photo_days_{len(requested_days)}.zip"
    )
    return StreamingResponse(
        iter_archive(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
