from __future__ import annotations

import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path, PurePosixPath

from .. import repository as repo
from .. import ssh_connection
from ..config import VALID_EXTENSIONS
from ..models import Capture
from ..storage import connection
from ..storage.folders import load_saved_folders
from ..utils.progress import progress_bar

# Maximum parallel SFTP connections when scanning multiple SSH sources.
# Each connection opens one SSH session + one SFTP channel, so keep this
# reasonable. 4 is enough for home/prosumer setups; raise if needed.
SSH_SCAN_WORKERS = 4


def _progreso_OLD(iterable, description: str = "", total: int | None = None):
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
    """Load metadata from the database, keyed by source_path."""
    try:
        raw = repo.load_captures()
        captures = [Capture.from_dict(item) for item in raw]
        return {c.source_path: c for c in captures}
    except Exception as e:
        print(f"⚠️ Could not load existing metadata: {e}\n")
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
            files = client.list_files_recursive(ruta_remota, list(VALID_EXTENSIONS))
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
            capture_date="",        # filled by EXIF during classify
            source_path=f"ssh://{alias}{f['ruta']}",
            ssh_alias=alias,
            ssh_remote_path=f["ruta"],
        ))
    return captures


def sync_captures() -> None:
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
            mounted = connection.is_mounted(c["letra"])
            status = "✅ mounted" if mounted else "⚠️ NOT mounted right now"
            alias = c.get("alias", c["letra"])
            ip_port = f"{c.get('ip')}:{c.get('puerto')}"
            print(f"  {c['letra']} ({alias} — {ip_port}): {status}")
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
                print(f"🔍 Will scan SSH server: {c['alias']} "
                      f"({c['usuario']}@{c['host']}:{c['ruta_remota']})")
            print(f"\n⚡ Scanning {len(ssh_sources)} server(s) in parallel "
                  f"(max {SSH_SCAN_WORKERS} concurrent)...\n")

            workers = min(SSH_SCAN_WORKERS, len(ssh_sources))
            results: dict[str, list[Capture]] = {}
            errors: dict[str, str] = {}

            with ThreadPoolExecutor(max_workers=workers,
                                    thread_name_prefix="ssh-scan") as pool:
                future_to_alias = {
                    pool.submit(scan_ssh_server, c): c["alias"]  # type: ignore[arg-type]
                    for c in ssh_sources
                }
                for future in as_completed(future_to_alias):
                    alias = future_to_alias[future]
                    try:
                        results[alias] = future.result()
                        print(f"  ✅ {alias}: {len(results[alias])} file(s) found")
                    except Exception as e:
                        errors[alias] = str(e)
                        print(f"  ❌ {alias}: scan failed — {e}")

            # Merge in the original server order for deterministic output
            for c in ssh_sources:
                alias = c["alias"]
                if alias in results:
                    ssh_captures.extend(results[alias])

            if errors:
                print(f"\n⚠️ {len(errors)} server(s) could not be scanned: "
                      f"{', '.join(errors)}")
            print()

    previous = load_existing_metadata()
    current: dict[str, Capture] = {}
    new_count = 0
    unchanged = 0

    for file in progress_bar(local_files, description="Analyzing screenshots..."):
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

    for cap in progress_bar(ssh_captures, description="Analyzing screenshots on SSH servers..."):
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
        repo.upsert_captures([c.to_dict() for c in captures_list])
        print("-" * 50)
        print("✅ Success! Metadata extracted and dates corrected.")
    else:
        print("❌ No screenshots found to export.")


if __name__ == "__main__":
    sync_captures()
