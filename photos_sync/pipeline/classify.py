"""
classify.py — Step 3 of the pipeline: tag each Capture with one or more
categories derived from filename patterns, source path, file extension,
and EXIF metadata (no ML required).

Tags assigned (non-exclusive):
  screenshot        — system screenshots
  camera            — photos taken with the device camera
  screen_recording  — screen recordings
  whatsapp          — WhatsApp media
  telegram          — Telegram media
  instagram / social— Instagram / generic social-app content
  download          — files from the Downloads folder
  panorama          — panoramic photos (very wide aspect ratio)
  edited            — files with edit/crop/filter suffixes
  gif               — animated GIFs
  video             — video files (mp4, mov, avi, …)
  web_image         — webp and other web-optimised formats
  no_exif           — image has no EXIF data (likely screenshot or meme)
  has_gps           — image contains GPS coordinates
  portrait          — height > width
  landscape_photo   — width > height
  other             — nothing else matched
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import repository as repo
from ..models import Capture

# EXIF support (optional — gracefully degraded if Pillow is missing)
try:
    from PIL import ExifTags, Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


# ── Rule tables ───────────────────────────────────────────────────────────────

_FILENAME_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^Screenshot_',              re.I), "screenshot"),
    (re.compile(r'^Captura_',                 re.I), "screenshot"),
    (re.compile(r'^screencap',                re.I), "screenshot"),
    (re.compile(r'screen.?shot',              re.I), "screenshot"),
    (re.compile(r'^IMG_\d',                   re.I), "camera"),
    (re.compile(r'^DSC[_\d]',                 re.I), "camera"),
    (re.compile(r'^PXL_',                     re.I), "camera"),   # Google Pixel
    (re.compile(r'^PANO_',                    re.I), "panorama"),
    (re.compile(r'panoram',                   re.I), "panorama"),
    (re.compile(r'screen.?record',            re.I), "screen_recording"),
    (re.compile(r'^VID_\d{8}',               re.I), "screen_recording"),
    (re.compile(r'[-_](edit|crop|filter|retouched)', re.I), "edited"),
    (re.compile(r'IMG-\d{8}-WA\d',           re.I), "whatsapp"),
    (re.compile(r'VID-\d{8}-WA\d',           re.I), "whatsapp"),
    (re.compile(r'whatsapp',                  re.I), "whatsapp"),
]

_PATH_RULES: list[tuple[str, str]] = [
    ("WhatsApp",           "whatsapp"),
    ("whatsapp",           "whatsapp"),
    ("Telegram",           "telegram"),
    ("Instagram",          "social"),
    ("Download",           "download"),
    ("/Camera",            "camera"),
    ("DCIM",               "camera"),
    ("Screenshots",        "screenshot"),
    ("Screen recordings",  "screen_recording"),
    ("ScreenRecordings",   "screen_recording"),
]

_VIDEO_EXTENSIONS: set[str] = {"mp4", "mov", "avi", "mkv", "3gp", "webm", "flv"}
_WEB_EXTENSIONS:   set[str] = {"webp", "avif"}

_SCREEN_SIZES: set[tuple[int, int]] = {
    (1080, 2340), (1080, 2400), (1080, 2408),
    (1080, 1920), (720, 1560),  (1440, 3040),
}


# ── EXIF helpers ──────────────────────────────────────────────────────────────

def _exif_tags(path: Path) -> dict:
    if not _PIL_OK:
        return {}
    try:
        with Image.open(path) as img:
            raw = img._getexif()  # type: ignore[attr-defined]
        if not raw:
            return {}
        return {ExifTags.TAGS.get(k, k): v for k, v in raw.items()}
    except Exception:
        return {}


def _gps_decimal(coord, ref: str) -> float | None:
    """Convert EXIF GPS DMS tuple to signed decimal degrees."""
    try:
        d, m, s = coord
        # IFDRational or plain numbers
        d = float(d)
        m = float(m)
        s = float(s)
        decimal = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 7)
    except Exception:
        return None


def _extract_gps(exif: dict) -> tuple[float, float] | None:
    """Return (lat, lon) from EXIF GPSInfo, or None."""
    gps = exif.get("GPSInfo")
    if not gps:
        return None
    try:
        from PIL.ExifTags import GPSTAGS
        gps_named = {GPSTAGS.get(k, k): v for k, v in gps.items()}
    except Exception:
        return None
    lat = _gps_decimal(gps_named.get("GPSLatitude"), gps_named.get("GPSLatitudeRef", "N"))
    lon = _gps_decimal(gps_named.get("GPSLongitude"), gps_named.get("GPSLongitudeRef", "E"))
    if lat is None or lon is None:
        return None
    return (lat, lon)


# Cache reverse geocode results in memory (lat/lon rounded to 2 decimals → city)
_geocode_cache: dict[tuple[float, float], str] = {}


def _reverse_geocode(lat: float, lon: float) -> str:
    """Return city name for coordinates using Nominatim (no API key needed).
    Returns empty string if geopy is not installed or lookup fails."""
    key = (round(lat, 2), round(lon, 2))
    if key in _geocode_cache:
        return _geocode_cache[key]
    try:
        from geopy.geocoders import Nominatim  # type: ignore[import]
        gc = Nominatim(user_agent="photos_sync/0.2")
        location = gc.reverse((lat, lon), exactly_one=True, language="en", timeout=5)
        if location and location.raw:
            addr = location.raw.get("address", {})
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("municipality")
                or addr.get("county")
                or ""
            )
            _geocode_cache[key] = city
            return city
    except Exception:
        pass
    _geocode_cache[key] = ""
    return ""


def _dimensions(path: Path) -> tuple[int, int] | None:
    if not _PIL_OK:
        return None
    try:
        with Image.open(path) as img:
            return img.size  # (width, height)
    except Exception:
        return None


# ── Core tagger ───────────────────────────────────────────────────────────────

def classify_one(cap: Capture) -> list[str]:
    """Apply all rules to one Capture. Returns a sorted, deduplicated tag list.

    This is the public, testable function. classify_captures() calls it for
    every Capture in the database.
    """
    tags: set[str] = set(cap.tags)

    # 1. Filename patterns
    for pattern, tag in _FILENAME_RULES:
        if pattern.search(cap.filename):
            tags.add(tag)

    # 2. Source-path (or ssh_remote_path when set) directory patterns
    #    Normalise backslashes so Windows paths work too.
    path_to_check = (cap.ssh_remote_path or cap.source_path).replace("\\", "/")
    for substr, tag in _PATH_RULES:
        if substr in path_to_check:
            tags.add(tag)

    # 3. Extension-based
    ext = cap.extension.lower().lstrip(".")
    if ext == "gif":
        tags.add("gif")
    elif ext in _VIDEO_EXTENSIONS:
        tags.add("video")
    elif ext in _WEB_EXTENSIONS:
        tags.add("web_image")

    # 4. EXIF + dimensions (local files only, requires Pillow)
    local: Path | None = None
    if cap.dest_path:
        local = Path(cap.dest_path)
    elif not cap.source_path.startswith("ssh://"):
        local = Path(cap.source_path.replace("\\", "/"))

    if local and local.exists():
        exif = _exif_tags(local)

        if not exif:
            tags.add("no_exif")
        if "GPSInfo" in exif:
            tags.add("has_gps")
            gps = _extract_gps(exif)
            if gps:
                cap.gps_lat, cap.gps_lon = gps
                city = _reverse_geocode(gps[0], gps[1])
                if city:
                    cap.city = city
        if exif.get("Make") or exif.get("Model"):
            tags.add("camera")

        dims = _dimensions(local)
        if dims:
            w, h = dims
            if w > 0 and h > 0:
                ratio = w / h
                if ratio >= 2.0:
                    tags.add("panorama")
                elif h > w:
                    tags.add("portrait")
                elif w > h:
                    tags.add("landscape_photo")
                if (w, h) in _SCREEN_SIZES and not exif:
                    tags.add("screenshot")

    # 5. Fallback
    if not tags:
        tags.add("other")

    return sorted(tags)


# ── Pipeline step ─────────────────────────────────────────────────────────────

def classify_captures() -> None:
    """Load captures from DB, apply rule-based tags, save back to DB."""
    print("Reading captures from database...\n")

    raw = repo.load_captures()
    if raw is None:
        print("❌ No captures in database. Run step 1 (download) first.")
        return
    if not isinstance(raw, list):
        print("❌ Database error. Run step 1 (download) again.")
        return
    if not raw:
        print("❌ No captures to classify.")
        return

    if _PIL_OK:
        print("✅ Pillow available — EXIF + dimension analysis enabled.\n")
    else:
        print("⚠️  Pillow not installed — filename/path rules only.\n"
              "    Install with: pip install Pillow\n")

    captures = [Capture.from_dict(d) for d in raw]
    tag_counts: dict[str, int] = {}

    for cap in captures:
        cap.tags = classify_one(cap)
        for t in cap.tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    repo.upsert_captures([c.to_dict() for c in captures])

    print("-" * 55)
    print("CLASSIFICATION SUMMARY:")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        print(f"  {tag:<20} {bar} {count}")
    print(f"\n✅ Tagged {len(captures)} captures — "
          f"{len(tag_counts)} distinct tag(s).")


if __name__ == "__main__":
    classify_captures()
