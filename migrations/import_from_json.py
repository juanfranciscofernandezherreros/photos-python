#!/usr/bin/env python3
"""
migrations/import_from_json.py
──────────────────────────────
One-time migration: reads all existing JSON data files from
~/PhotosSync/data/ and imports them into the PostgreSQL database.

Run ONCE after upgrading from the JSON-based version:

    python -m photos_sync.migrations.import_from_json

Or directly:

    python migrations/import_from_json.py

Prerequisites:
    • DATABASE_URL env var set (or default postgresql://localhost/photos_sync)
    • Database already created: createdb photos_sync
    • Tables will be created automatically if they don't exist
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_json(path: str | Path, default=None):
    """Safely load a JSON file, returning default on any error."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data
    except Exception:
        return default


def migrate():
    # Bootstrap database
    from photos_sync.db import get_engine, init_db
    from photos_sync import repository as repo

    print("🔌 Connecting to database…")
    engine = get_engine()
    init_db(engine)
    print(f"   Engine: {engine.url}\n")

    # Paths to legacy JSON files
    base = Path.home() / "PhotosSync" / "data"
    files = {
        "captures":    base / "metadatos_screenshots.json",
        "folders":     base / "carpetas_screenshots.json",
        "destination": base / "destino_guardado.json",
        "summaries":   base / "resumen_por_dia.json",
        "webdav":      base / "conexiones_webdav.json",
        "ssh":         base / "conexiones_ssh.json",
        "favourites":  base / "favourites.json",
        "albums":      base / "albums.json",
    }

    # ── Captures ─────────────────────────────────────────────────────────────
    raw_captures = _load_json(files["captures"], default=[])
    if raw_captures:
        print(f"📸 Importing {len(raw_captures)} captures…")
        repo.upsert_captures(raw_captures)
        print(f"   ✅ {len(raw_captures)} captures imported.")
    else:
        print("   ⚠️  captures: file not found or empty — skipping.")

    # ── Favourites ────────────────────────────────────────────────────────────
    fav_paths = _load_json(files["favourites"], default=[])
    if fav_paths and isinstance(fav_paths, list):
        print(f"❤️  Marking {len(fav_paths)} favourites…")
        marked = 0
        for p in fav_paths:
            if not repo.get_capture_by_dest(p):
                # Photo exists on disk but not in captures — insert minimal record
                _f = Path(p)
                if _f.is_file():
                    repo.upsert_captures([{
                        "id": p, "archivo": _f.name,
                        "formato": _f.suffix.lstrip("."),
                        "tamano_mb": round(_f.stat().st_size / 1048576, 2),
                        "mtime": _f.stat().st_mtime,
                        "fecha_captura": "", "ruta_original": "",
                        "ruta_destino": p, "tags": [],
                    }])
            repo.set_favourite(p, True)
            marked += 1
        print(f"   ✅ {marked} favourites marked.")
    else:
        print("   ⚠️  favourites: file not found or empty — skipping.")

    # ── Source folders ────────────────────────────────────────────────────────
    folders = _load_json(files["folders"], default=[])
    if folders and isinstance(folders, list):
        print(f"📁 Importing {len(folders)} source folders…")
        repo.save_source_folders([str(f) for f in folders])
        print(f"   ✅ {len(folders)} folders imported.")
    else:
        print("   ⚠️  folders: file not found or empty — skipping.")

    # ── Destination ───────────────────────────────────────────────────────────
    dest = _load_json(files["destination"], default={})
    if dest and isinstance(dest, dict):
        tipo = dest.get("tipo", "local")
        if tipo == "ssh" and dest.get("alias"):
            repo.save_destination_ssh(dest["alias"])
            print(f"   ✅ Destination: SSH → {dest['alias']}")
        elif tipo == "local":
            ruta = dest.get("ruta") or dest.get("destino", "")
            repo.save_destination_local(ruta)
            print(f"   ✅ Destination: local → {ruta}")
    else:
        print("   ⚠️  destination: file not found or empty — skipping.")

    # ── Day summaries ─────────────────────────────────────────────────────────
    summaries = _load_json(files["summaries"], default=[])
    if summaries and isinstance(summaries, list):
        print(f"📅 Importing {len(summaries)} day summaries…")
        repo.upsert_summaries(summaries)
        print(f"   ✅ {len(summaries)} summaries imported.")
    else:
        print("   ⚠️  summaries: file not found or empty — skipping.")

    # ── SSH connections ───────────────────────────────────────────────────────
    ssh_conns = _load_json(files["ssh"], default=[])
    if ssh_conns and isinstance(ssh_conns, list):
        print(f"🖧  Importing {len(ssh_conns)} SSH connections…")
        repo.save_ssh_connections(ssh_conns)
        print(f"   ✅ {len(ssh_conns)} SSH connections imported.")
    else:
        print("   ⚠️  SSH connections: file not found or empty — skipping.")

    # ── WebDAV connections ────────────────────────────────────────────────────
    webdav_conns = _load_json(files["webdav"], default=[])
    if webdav_conns and isinstance(webdav_conns, list):
        print(f"📡 Importing {len(webdav_conns)} WebDAV connections…")
        for c in webdav_conns:
            repo.add_or_update_webdav(
                c.get("letra", ""), c.get("ip", ""),
                c.get("puerto", "8080"), c.get("alias", ""),
            )
        print(f"   ✅ {len(webdav_conns)} WebDAV connections imported.")
    else:
        print("   ⚠️  WebDAV connections: file not found or empty — skipping.")

    # ── Albums ────────────────────────────────────────────────────────────────
    albums = _load_json(files["albums"], default=[])
    if albums and isinstance(albums, list):
        print(f"🗂️  Importing {len(albums)} albums…")
        count = 0
        for a in albums:
            album_id = a.get("id", "")
            name = a.get("name", "Untitled")
            created = a.get("created", "")
            photos = a.get("photos", []) or []
            cover = a.get("cover")
            if not album_id:
                continue
            repo.create_album(album_id, name, created)
            if cover:
                repo.update_album_cover(album_id, cover)
            if photos:
                repo.album_add_photos(album_id, photos)
            count += 1
        print(f"   ✅ {count} albums imported.")
    else:
        print("   ⚠️  albums: file not found or empty — skipping.")

    print("\n✅ Migration complete!")
    print("   You can now delete the JSON files in ~/PhotosSync/data/ if you wish.")
    print("   Keep a backup first: cp -r ~/PhotosSync/data/ ~/PhotosSync/data.bak/\n")


if __name__ == "__main__":
    migrate()
