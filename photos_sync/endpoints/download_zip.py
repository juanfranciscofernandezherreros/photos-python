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

@router.get("/api/photos/download-zip")
def download_zip(
    paths: str,
    _auth: dict = Depends(require_login),
):
    """Stream a ZIP archive containing the requested photos.

    Query param: paths — comma-separated list of absolute file paths.
    Only paths inside allowed bases are included (others silently skipped).
    The ZIP is streamed so large selections don't need to be buffered in memory.
    """
    import io
    import zipfile

    from fastapi.responses import StreamingResponse

    raw_paths = [p.strip() for p in paths.split(",") if p.strip()]
    allowed = [p for p in raw_paths if _is_allowed(Path(p)) and Path(p).is_file()]

    if not allowed:
        raise HTTPException(404, "No valid photos found in selection")

    def _iter_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED,
                             allowZip64=True) as zf:
            seen_names: dict[str, int] = {}
            for fpath in allowed:
                name = Path(fpath).name
                # Deduplicate: photo_001.jpg → photo_001_2.jpg etc.
                if name in seen_names:
                    seen_names[name] += 1
                    stem, ext = Path(name).stem, Path(name).suffix
                    name = f"{stem}_{seen_names[name]}{ext}"
                else:
                    seen_names[name] = 1
                zf.write(fpath, arcname=name)
        buf.seek(0)
        yield from buf

    filename = f"photos_{len(allowed)}.zip"
    return StreamingResponse(
        _iter_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
