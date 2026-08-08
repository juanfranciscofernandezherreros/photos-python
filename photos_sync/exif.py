"""Safe, normalized EXIF extraction for local photo files."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    """Convert vendor EXIF values to bounded JSON-compatible values."""
    if depth > 4:
        return "<nested value>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, bytes):
        return f"<binary {len(value)} bytes>"
    if isinstance(value, dict):
        return {
            str(key): _safe_value(item, depth=depth + 1)
            for key, item in list(value.items())[:250]
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in value[:250]]
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)[:1000]


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip("\x00 ") or None
    return str(value).strip("\x00 ") or None


def _float(value: Any) -> float | None:
    try:
        return round(float(value), 8)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _rational_text(value: Any) -> str | None:
    if value is None:
        return None
    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if numerator is not None and denominator:
        return f"{numerator}/{denominator}"
    return _text(value)


def _gps_decimal(coordinates: Any, reference: Any) -> float | None:
    try:
        degrees, minutes, seconds = (float(part) for part in coordinates)
        decimal = degrees + minutes / 60 + seconds / 3600
        if str(reference).upper() in {"S", "W"}:
            decimal = -decimal
        return round(decimal, 7)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def _named_exif(exif: Any) -> dict[str, Any]:
    named = {str(ExifTags.TAGS.get(key, key)): value for key, value in exif.items()}
    ifd_enum = getattr(ExifTags, "IFD", None)
    if ifd_enum is not None and hasattr(exif, "get_ifd"):
        try:
            detail = exif.get_ifd(ifd_enum.Exif)
            named.update({str(ExifTags.TAGS.get(key, key)): value for key, value in detail.items()})
        except (KeyError, TypeError, ValueError):
            pass
        try:
            gps = exif.get_ifd(ifd_enum.GPSInfo)
            if gps:
                named["GPSInfo"] = {
                    str(ExifTags.GPSTAGS.get(key, key)): value
                    for key, value in gps.items()
                }
        except (KeyError, TypeError, ValueError):
            pass
    elif isinstance(named.get("GPSInfo"), dict):
        named["GPSInfo"] = {
            str(ExifTags.GPSTAGS.get(key, key)): value
            for key, value in named["GPSInfo"].items()
        }
    return named


def exif_datetime_to_iso(value: Any) -> str | None:
    """Convert the common EXIF timestamp format to an ISO local timestamp."""
    text = _text(value)
    if not text:
        return None
    for pattern in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def extract_photo_exif(path: Path) -> dict[str, Any]:
    """Extract dimensions, normalized fields, GPS, and bounded raw EXIF."""
    extracted_at = datetime.now(UTC).replace(tzinfo=None)
    result: dict[str, Any] = {
        "file_path": str(path),
        "file_mtime": 0.0,
        "extracted_at": extracted_at,
        "has_exif": False,
        "width": None,
        "height": None,
        "camera_make": None,
        "camera_model": None,
        "lens_model": None,
        "software": None,
        "artist": None,
        "copyright": None,
        "date_time_original": None,
        "offset_time_original": None,
        "orientation": None,
        "exposure_time": None,
        "f_number": None,
        "iso_speed": None,
        "focal_length_mm": None,
        "flash": None,
        "white_balance": None,
        "metering_mode": None,
        "exposure_program": None,
        "gps_lat": None,
        "gps_lon": None,
        "gps_altitude_m": None,
        "raw": {},
        "error": None,
    }
    try:
        result["file_mtime"] = path.stat().st_mtime
        with Image.open(path) as image:
            result["width"], result["height"] = image.size
            named = _named_exif(image.getexif())
    except FileNotFoundError:
        result["error"] = "File not found"
        return result
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        result["error"] = f"Unsupported or unreadable image: {exc}"
        return result

    result["has_exif"] = bool(named)
    result["camera_make"] = _text(named.get("Make"))
    result["camera_model"] = _text(named.get("Model"))
    result["lens_model"] = _text(named.get("LensModel"))
    result["software"] = _text(named.get("Software"))
    result["artist"] = _text(named.get("Artist"))
    result["copyright"] = _text(named.get("Copyright"))
    result["date_time_original"] = _text(
        named.get("DateTimeOriginal") or named.get("DateTimeDigitized") or named.get("DateTime")
    )
    result["offset_time_original"] = _text(
        named.get("OffsetTimeOriginal") or named.get("OffsetTime")
    )
    result["orientation"] = _integer(named.get("Orientation"))
    result["exposure_time"] = _rational_text(named.get("ExposureTime"))
    result["f_number"] = _float(named.get("FNumber"))
    result["iso_speed"] = _integer(
        named.get("PhotographicSensitivity") or named.get("ISOSpeedRatings")
    )
    result["focal_length_mm"] = _float(named.get("FocalLength"))
    result["flash"] = _text(named.get("Flash"))
    result["white_balance"] = _text(named.get("WhiteBalance"))
    result["metering_mode"] = _text(named.get("MeteringMode"))
    result["exposure_program"] = _text(named.get("ExposureProgram"))

    gps: dict[str, Any] = {}
    gps_value = named.get("GPSInfo")
    if isinstance(gps_value, dict):
        gps = gps_value
    result["gps_lat"] = _gps_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef", "N"))
    result["gps_lon"] = _gps_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef", "E"))
    altitude = _float(gps.get("GPSAltitude"))
    if altitude is not None and _integer(gps.get("GPSAltitudeRef")) == 1:
        altitude = -altitude
    result["gps_altitude_m"] = altitude
    result["raw"] = {
        key: _safe_value(value)
        for key, value in sorted(named.items())
        if key not in {"MakerNote"}
    }
    return result
