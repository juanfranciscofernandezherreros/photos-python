import uuid
import re
from datetime import datetime
from pathlib import Path, PurePosixPath

from .folders import load_saved_folders
from .config import METADATA_JSON, VALID_EXTENSIONS
from .json_io import read_json, write_json
from .models import Capture
from . import connection, ssh_connection


def _progreso(iterable, description: str = "", total: int | None = None):
    """Progress bar writing to sys.stdout (replaces rich.progress.track)."""
    items = list(iterable)
    n = total or len(items)
    for i, item in enumerate(items, 1):
        if n > 0:
            pct = int(i / n * 100)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r{description} [{bar}] {i}/{n} ({pct}%)", end="", flush=True)
        yield item
    if n > 0:
        print()


def load_existing_metadata() -> dict[str, Capture]:
    """Load the saved metadata JSON and return a dict keyed by source_path."""
    lista_previa = read_json(METADATA_JSON)
    if not isinstance(lista_previa, list):
        return {}
    try:
        captures = [Capture.from_dict(item) for item in lista_previa]
        return {c.source_path: c for c in captures}
    except (KeyError, TypeError):
        print(f"⚠️ Existing '{METADATA_JSON}' is corrupt, it will be regenerated from scratch.\n")
        return {}


def get_actual_date(filename: str, mtime_fallback: float) -> str:
    """Extract the capture date from the filename (Screenshot_20231024_153020).
    More reliable than filesystem mtime because WebDAV often corrupts timestamps."""
    # Full datetime: year, month, day, hour, minute, second
    match = re.search(r'(20\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})', filename)
    if match:
        a, m, d, h, mn, s = match.groups()
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31 and 0 <= int(h) <= 23:
            return f"{a}-{m}-{d} {h}:{mn}:{s}"

    # Date only: year, month, day
    match = re.search(r'(20\d{2})\D*(\d{2})\D*(\d{2})', filename)
    if match:
        a, m, d = match.groups()
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{a}-{m}-{d} 12:00:00"

    # Fallback to filesystem mtime
    return datetime.fromtimestamp(mtime_fallback).strftime('%Y-%m-%d %H:%M:%S')


def scan_ssh_server(conn: ssh_connection.SSHConnection) -> list[Capture]:
    """Connect via SFTP to a Linux server configured as source (or 'ambos')
    and return a list of Capture objects with ssh_alias/ssh_remote_path set
    so organize.py knows to download them via SFTP."""
    alias = conn["alias"]
    ruta_remota = conn["ruta_remota"]

    try:
        with ssh_connection.SSHClient(conn) as client:
            files = client.list_files_recursive(ruta_remota, VALID_EXTENSIONS)
    except Exception as e:
        print(f"⚠️ Could not scan SSH server '{alias}' ({conn['host']}): {e}")
        return []

    captures = []
    for f in files:
        nombre = PurePosixPath(f["ruta"]).name
        captures.append(Capture(
            id=str(uuid.uuid4()),   # temporary; may be replaced by existing id below
            filename=nombre,
            extension=PurePosixPath(nombre).suffix.lower().replace('.', ''),
            size_mb=round(f["tamano"] / (1024 * 1024), 2),
            mtime=f["mtime"],
            capture_date="",        # filled in export_metadata_json
            source_path=f"ssh://{alias}{f['ruta']}",
            ssh_alias=alias,
            ssh_remote_path=f["ruta"],
        ))
    return captures


def export_metadata_json() -> None:
    print("Searching for screenshots on connected drives and extracting metadata...\n")

    folders = load_saved_folders()
    ssh_sources = ssh_connection.connections_by_role("origen")

    if not folders and not ssh_sources:
        print("❌ No connection or folder configured yet. Use the WebDAV or "
              "SSH section in the main window to connect a phone or server first.")
        return

    saved_connections = connection.load_connections()
    if saved_connections:
        for c in saved_connections:
            status = "✅ mounted" if connection.is_mounted(c["letra"]) else "⚠️ NOT mounted right now"
            print(f"  {c['letra']} ({c.get('alias', c['letra'])} — {c.get('ip')}:{c.get('puerto')}): {status}")
        print()

    local_files: list[Path] = []
    for folder in folders:
        if not (folder.exists() and folder.is_dir()):
            print(f"⚠️ Subfolder not found on drive: {folder}")
            continue
        print(f"✅ Extracting data from: {folder}")
        try:
            for candidate in folder.rglob('*'):
                try:
                    if candidate.is_file() and candidate.suffix.lower() in VALID_EXTENSIONS:
                        local_files.append(candidate)
                except OSError:
                    pass
        except OSError:
            pass

    ssh_captures: list[Capture] = []
    if ssh_sources:
        if not ssh_connection.paramiko_available():
            print("⚠️ SSH servers are configured as source, but 'paramiko' is missing. "
                  "Install it with: pip install paramiko\n")
        else:
            for c in ssh_sources:
                print(f"✅ Extracting data from SSH server: {c['alias']} "
                      f"({c['usuario']}@{c['host']}:{c['ruta_remota']})")
                ssh_captures.extend(scan_ssh_server(c))
            print()

    previous = load_existing_metadata()
    current: dict[str, Capture] = {}
    new_count = 0
    unchanged = 0

    for file in _progreso(local_files, description="Analyzing screenshots..."):
        source = str(file)
        try:
            stats = file.stat()
            size_mb = round(stats.st_size / (1024 * 1024), 2)
            prev = previous.get(source)

            if prev and prev.size_mb == size_mb and prev.mtime == stats.st_mtime:
                current[source] = prev
                unchanged += 1
                continue

            capture_date = get_actual_date(file.name, stats.st_mtime)
            capture_id = prev.id if prev else str(uuid.uuid4())

            current[source] = Capture(
                id=capture_id,
                filename=file.name,
                extension=file.suffix.lower().replace('.', ''),
                size_mb=size_mb,
                mtime=stats.st_mtime,
                capture_date=capture_date,
                source_path=source,
            )
            new_count += 1

        except OSError:
            continue

    for cap in _progreso(ssh_captures, description="Analyzing screenshots on SSH servers..."):
        source = cap.source_path
        prev = previous.get(source)

        if prev and prev.size_mb == cap.size_mb and prev.mtime == cap.mtime:
            current[source] = prev
            unchanged += 1
            continue

        cap.capture_date = get_actual_date(cap.filename, cap.mtime)
        cap.id = prev.id if prev else cap.id
        # preserve existing dest_path and zip_path if already organized
        if prev:
            cap.dest_path = prev.dest_path
            cap.zip_path = prev.zip_path
        current[source] = cap
        new_count += 1

    captures_list = list(current.values())

    if captures_list:
        write_json(METADATA_JSON, [c.to_dict() for c in captures_list])
        print("-" * 50)
        print(f"✅ Success! Metadata extracted and dates corrected.")
    else:
        print("❌ No screenshots found to export.")


if __name__ == "__main__":
    export_metadata_json()
