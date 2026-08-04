"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from .. import web_server as _shared

# Endpoint implementations retain access to the application's shared services,
# models and state without duplicating business infrastructure.
globals().update({
    name: value
    for name, value in vars(_shared).items()
    if not name.startswith("__")
})

router = APIRouter()

@router.post("/api/photos/fix-dates")
def fix_capture_dates(_auth: dict = Depends(require_admin)):
    """Re-derive capture_date for every photo from its filename.

    Safe to run multiple times. upsert_captures always extracts the date
    from the filename, so re-upserting every row corrects any bad dates.
    """
    from ..utils.dates import extract_date_from_filename

    caps = repo.load_captures()
    updated = 0
    skipped_no_pattern = 0
    skipped_already_good = 0

    for c in caps:
        filename = c.get("archivo") or ""
        real_date = extract_date_from_filename(filename)
        if not real_date:
            skipped_no_pattern += 1
            continue

        current = (c.get("fecha_captura") or "").strip()
        if current and current[:19] == real_date[:19]:
            skipped_already_good += 1
            continue

        # Re-upsert — the repo will set the correct date from filename
        repo.upsert_captures([c])
        updated += 1

    return {
        "ok": True,
        "total": len(caps),
        "updated": updated,
        "skipped_no_pattern": skipped_no_pattern,
        "skipped_already_good": skipped_already_good,
    }
