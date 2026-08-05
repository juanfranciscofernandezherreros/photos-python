"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..web_server import (
    Depends,
    HTTPException,
    Path,
    _is_allowed,
    require_login,
)

router = APIRouter()

@router.get("/api/thumb")
def serve_thumbnail(path: str, size: int = 300, _auth: dict = Depends(require_login)):
    """Serve a cached JPEG thumbnail of a photo. Generates and caches it
    on first request under THUMBS_DIR/<hash>.jpg. Falls back to the full
    image if Pillow is unavailable."""
    import hashlib

    from fastapi.responses import FileResponse

    from ..config import THUMBS_DIR

    p = Path(path)
    if not _is_allowed(p):
        raise HTTPException(403, "Access denied")
    if not p.is_file():
        raise HTTPException(404, "File not found")

    # Pillow required for thumbnailing
    try:
        from PIL import Image
    except ImportError:
        # Graceful fallback: serve the original
        import mimetypes
        mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
        return FileResponse(p, media_type=mime)

    size = max(64, min(size, 1024))  # clamp

    # Cache key: absolute path + size + file mtime (so edits invalidate)
    try:
        mtime = int(p.stat().st_mtime)
    except OSError:
        mtime = 0
    key = f"{p.resolve()}|{size}|{mtime}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMBS_DIR / f"{digest}.jpg"

    if not thumb_path.exists():
        try:
            with Image.open(p) as img:
                rgb = img.convert("RGB")
                rgb.thumbnail((size, size), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)  # type: ignore[attr-defined]
                rgb.save(thumb_path, "JPEG", quality=82, optimize=True)
        except Exception:
            # If thumbnailing fails (corrupt file, unsupported), serve original
            import mimetypes
            mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
            return FileResponse(p, media_type=mime)

    return FileResponse(thumb_path, media_type="image/jpeg")
