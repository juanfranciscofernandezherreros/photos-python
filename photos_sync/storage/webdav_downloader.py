"""
webdav_downloader.py — Direct WebDAV HTTP download (no net use / drive letters).

Works on any platform including Linux/Docker containers where mounting
a network drive with 'net use' is not possible.

Uses only the standard library + requests (already a transitive dependency
via FastAPI/httpx), so no extra install is needed.

Public API
──────────
    list_remote_files(ip, port, remote_path, extensions) -> list[RemoteFile]
    download_to_local(ip, port, files, dest_dir, on_progress) -> list[Path]
    sync_webdav_connection(conn, dest_dir, on_progress) -> list[Path]
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET

# requests is already available (FastAPI pulls it in via httpx/starlette)
try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

WEBDAV_PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".webp", ".heic", ".mp4", ".mov",
}

# Default Android photo folders (checked on the WebDAV server)
DEFAULT_REMOTE_PATHS = [
    "/Pictures/Screenshots",
    "/DCIM/Screenshots",
    "/DCIM/Camera",
    "/Pictures",
]


@dataclass
class RemoteFile:
    href: str          # full URL path, e.g. /Pictures/Screenshots/IMG_001.jpg
    name: str          # filename only
    size: int          # bytes
    modified: str      # raw Last-Modified header value


def _propfind(base_url: str, path: str, depth: int = 1, timeout: int = 10) -> ET.Element | None:
    """Issue a WebDAV PROPFIND request and return the parsed XML root."""
    if not _REQUESTS_OK:
        raise RuntimeError("requests library is not installed")
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {
        "Depth":        str(depth),
        "Content-Type": "application/xml; charset=utf-8",
    }
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<propfind xmlns="DAV:">'
        '<prop><resourcetype/><getcontentlength/><getlastmodified/></prop>'
        '</propfind>'
    )
    try:
        r = _requests.request(
            "PROPFIND", url,
            headers=headers, data=body.encode(),
            timeout=timeout,
        )
        if r.status_code not in (200, 207):
            return None
        return ET.fromstring(r.content)
    except Exception:
        return None


def list_remote_files(
    ip: str,
    port: str | int,
    remote_path: str = "/",
    extensions: set[str] | None = None,
    timeout: int = 10,
) -> list[RemoteFile]:
    """Return all photo files found under remote_path on the WebDAV server."""
    if extensions is None:
        extensions = WEBDAV_PHOTO_EXTENSIONS

    base_url = f"http://{ip}:{port}"
    results: list[RemoteFile] = []
    _collect_files(base_url, remote_path, extensions, results, depth=0, max_depth=5, timeout=timeout)
    return results


def _collect_files(
    base_url: str,
    path: str,
    extensions: set[str],
    out: list[RemoteFile],
    depth: int,
    max_depth: int,
    timeout: int,
) -> None:
    if depth > max_depth:
        return
    root = _propfind(base_url, path, depth=1, timeout=timeout)
    if root is None:
        return

    ns = {"d": "DAV:"}
    for resp in root.findall("d:response", ns):
        href_el = resp.find("d:href", ns)
        if href_el is None:
            continue
        href = href_el.text or ""

        # Skip the directory itself
        if href.rstrip("/") == path.rstrip("/"):
            continue

        # Is it a collection (directory)?
        rt = resp.find(".//d:resourcetype/d:collection", ns)
        if rt is not None:
            _collect_files(base_url, href, extensions, out, depth + 1, max_depth, timeout)
            continue

        # It's a file — check extension
        name = Path(href).name
        if Path(name).suffix.lower() in extensions:
            size_el = resp.find(".//d:getcontentlength", ns)
            mod_el  = resp.find(".//d:getlastmodified", ns)
            out.append(RemoteFile(
                href=href,
                name=name,
                size=int(size_el.text or 0) if size_el is not None else 0,
                modified=(mod_el.text or "") if mod_el is not None else "",
            ))


def download_to_local(
    ip: str,
    port: str | int,
    files: list[RemoteFile],
    dest_dir: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    """Download a list of RemoteFiles to dest_dir.

    on_progress(current, total, filename) is called after each file.
    Returns list of downloaded local paths (skips already-existing files
    that are the same size).
    """
    if not _REQUESTS_OK:
        raise RuntimeError("requests library is not installed")

    dest_dir.mkdir(parents=True, exist_ok=True)
    base_url = f"http://{ip}:{port}"
    downloaded: list[Path] = []

    for idx, f in enumerate(files, 1):
        local = dest_dir / f.name
        # Skip if already downloaded and same size
        if local.exists() and local.stat().st_size == f.size and f.size > 0:
            downloaded.append(local)
            if on_progress:
                on_progress(idx, len(files), f.name)
            continue

        url = base_url.rstrip("/") + "/" + f.href.lstrip("/")
        try:
            r = _requests.get(url, stream=True, timeout=60)
            r.raise_for_status()
            tmp = local.with_suffix(local.suffix + ".part")
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(chunk_size=65536):
                    fh.write(chunk)
            tmp.replace(local)
            downloaded.append(local)
        except Exception as e:
            print(f"  ⚠️  Could not download {f.name}: {e}")

        if on_progress:
            on_progress(idx, len(files), f.name)

    return downloaded


def sync_webdav_connection(
    ip: str,
    port: str | int,
    dest_dir: Path,
    remote_paths: list[str] | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    """High-level helper: list all photos on the phone and download new ones.

    Tries DEFAULT_REMOTE_PATHS if remote_paths is not given.
    Returns all downloaded local file paths.
    """
    paths = remote_paths or DEFAULT_REMOTE_PATHS
    all_files: list[RemoteFile] = []
    seen_names: set[str] = set()

    print(f"\n🔍 Scanning WebDAV server at {ip}:{port}…")
    for rpath in paths:
        found = list_remote_files(ip, port, rpath)
        for f in found:
            if f.name not in seen_names:
                all_files.append(f)
                seen_names.add(f.name)
        if found:
            print(f"   {rpath}: {len(found)} photos found")

    if not all_files:
        print("   No photos found on the WebDAV server.")
        return []

    print(f"\n📥 Downloading {len(all_files)} photos to {dest_dir}…")
    downloaded = download_to_local(ip, port, all_files, dest_dir, on_progress)
    print(f"   ✅ {len(downloaded)} photos ready in {dest_dir}")
    return downloaded
