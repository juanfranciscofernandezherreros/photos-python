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

@router.get("/api/days")
def get_days(_auth: dict = Depends(require_login)):
    """Group all captures by date.

    Uses the captures table as the source of truth: every photo that has
    a row here appears in the gallery, no matter where it lives on disk
    (organized by YYYY/MM/DD, in /incoming, in a custom folder, etc).

    The date used to group is capture_date if present, otherwise the
    file's mtime, otherwise the file itself gets grouped under 'undated'.
    """
    from datetime import datetime as _dt

    # DB metadata: photo path → (capture_date, tags, city, gps, is_favourite)
    caps = repo.load_captures()

    # DB summaries provide zip_path for a given date if the pipeline ran
    summary_by_date: dict[str, dict] = {}
    for s in repo.load_summaries() or []:
        if s.get("fecha"):
            summary_by_date[s["fecha"]] = s

    # Group by YYYY-MM-DD
    by_date: dict[str, list[dict]] = {}
    for c in caps:
        fpath = c.get("ruta_destino") or c.get("ruta_original") or ""
        if not fpath:
            continue

        # Pick the best date we have for this photo
        date_str = ""
        cap_date = (c.get("fecha_captura") or "").strip()
        if cap_date and len(cap_date) >= 10:
            date_str = cap_date[:10]     # ISO 'YYYY-MM-DD...'
        elif c.get("mtime"):
            try:
                date_str = _dt.fromtimestamp(float(c["mtime"])).strftime("%Y-%m-%d")
            except Exception:
                pass
        if not date_str:
            date_str = "undated"

        by_date.setdefault(date_str, []).append({
            "path":    fpath,
            "size_mb": c.get("tamano_mb", 0) or 0,
        })

    days = []
    for date_str, entries in by_date.items():
        year, month, day = (date_str.split("-") + ["", "", ""])[:3] \
                           if date_str != "undated" else ("", "", "")
        # Best-effort: point 'destino' at the folder of the first photo
        first_path = entries[0]["path"] if entries else ""
        first_dir  = str(Path(first_path).parent) if first_path else ""
        # The day-card cover is returned with the summary so the frontend does
        # not need one additional /api/days/{date}/photos request per day.
        cover_path = min(
            (entry["path"] for entry in entries),
            key=lambda path: Path(path).name.casefold(),
            default="",
        )
        extra = summary_by_date.get(date_str, {})
        days.append({
            "fecha":            date_str,
            "anio":             year,
            "mes":              month,
            "dia":              day,
            "cantidad_fotos":   len(entries),
            "tamano_total_mb":  round(sum(e["size_mb"] for e in entries), 2),
            "destino":          first_dir,
            "ruta_zip":         extra.get("ruta_zip", ""),
            "cover_path":       cover_path,
        })

    days.sort(key=lambda d: d["fecha"], reverse=True)
    total_photos = sum(d["cantidad_fotos"] for d in days)
    total_mb     = round(sum(d["tamano_total_mb"] for d in days), 1)
    return {
        "days":         days,
        "total_photos": total_photos,
        "total_mb":     total_mb,
        "total_days":   len(days),
    }
