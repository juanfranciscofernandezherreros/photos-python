"""
repository.py — All data-access functions for Photos Sync.

Every function that used to call read_json() / write_json() now calls
one of these instead. The database engine comes from db.get_engine();
tests inject a SQLite in-memory engine via db.set_engine().

Public surface (grouped by entity):

  SSH connections
    load_ssh_connections()
    save_ssh_connections(conns)          # replaces write_json(SSH_CONNECTIONS_JSON)
    add_or_update_ssh(...)
    remove_ssh(alias)
    get_ssh(alias)
    ssh_by_role(role)

  WebDAV connections
    load_webdav_connections()
    add_or_update_webdav(letter, ip, port, alias)
    remove_webdav(letter)

  Source folders
    load_source_folders()  -> list[str]
    save_source_folders(paths)

  Destination config
    load_destination_config()  -> dict
    save_destination_local(path)
    save_destination_ssh(alias)
    clear_destination()

  Captures
    load_captures()        -> list[dict]
    save_capture(cap_dict)
    upsert_captures(caps)  # bulk upsert
    get_capture_by_dest(dest_path) -> dict | None

  Favourites  (stored as captures.is_favourite)
    load_favourites()      -> list[str]   (dest_path of starred photos)
    set_favourite(path, flag)
    bulk_set_favourite(paths, flag)

  Albums
    load_albums()          -> list[dict]
    get_album(album_id)    -> dict | None
    create_album(album_dict)
    update_album(album_id, **fields)
    delete_album(album_id)
    album_add_photos(album_id, paths)
    album_remove_photos(album_id, paths)
    album_photo_paths(album_id) -> list[str]

  Day summaries
    load_summaries()       -> list[dict]
    upsert_summary(summary_dict)
    upsert_summaries(summaries)

  Tags / Cities  (computed from captures)
    load_tags()            -> list[dict]
    load_cities()          -> list[dict]
    photos_by_city(city)   -> list[dict]
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import case, delete, func, insert, select, update

from .db import (
    decode_tags,
    encode_tags,
    get_engine,
    t_album_photos,
    t_albums,
    t_captures,
    t_destination,
    t_folders,
    t_ssh,
    t_summaries,
    t_trash,
    t_users,
    t_webdav,
)

# ── Internal helper ───────────────────────────────────────────────────────────

def _conn():
    """Context manager: open a connection and auto-commit on exit."""
    return get_engine().begin()          # begin() auto-commits on __exit__


# ─────────────────────────────────────────────────────────────────────────────
# SSH connections
# ─────────────────────────────────────────────────────────────────────────────

def load_ssh_connections() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(t_ssh)).mappings().all()
    return [
        {
            "alias":                r["alias"],
            "host":                 r["host"],
            "puerto":               r["port"],
            "usuario":              r["username"],
            "ruta_remota":          r["remote_path"],
            "ruta_remota_destino":  r["remote_path_dest"],
            "clave_privada":        r["private_key_path"],
            "tiene_clave":          bool(r["private_key_path"]),
            "rol":                  r["role"],
        }
        for r in rows
    ]


def save_ssh_connections(conns: list[dict]) -> None:
    """Full replace — delete all rows and re-insert."""
    with _conn() as conn:
        conn.execute(delete(t_ssh))
        for c in conns:
            conn.execute(insert(t_ssh).values(
                alias=c["alias"],
                host=c["host"],
                port=c.get("puerto", 22),
                username=c.get("usuario", ""),
                remote_path=c.get("ruta_remota", ""),
                remote_path_dest=c.get("ruta_remota_destino", ""),
                private_key_path=c.get("clave_privada", ""),
                role=c.get("rol", "origen"),
            ))


def add_or_update_ssh(
    alias: str, host: str, puerto: int, usuario: str,
    ruta_remota: str, clave_privada: str = "",
    rol: str = "origen", ruta_remota_destino: str = "",
) -> list[dict]:
    from .ssh.validation import DEFAULT_SSH_PORT, VALID_ROLES, validate_ambos_role
    if rol not in VALID_ROLES:
        rol = "origen"
    ruta_remota = ruta_remota.rstrip("/") or ruta_remota
    ruta_remota_destino = ruta_remota_destino.strip().rstrip("/")
    validate_ambos_role(rol, ruta_remota, ruta_remota_destino)
    with _conn() as conn:
        conn.execute(delete(t_ssh).where(t_ssh.c.alias == alias))
        conn.execute(insert(t_ssh).values(
            alias=alias, host=host, port=puerto or DEFAULT_SSH_PORT,
            username=usuario, remote_path=ruta_remota,
            remote_path_dest=ruta_remota_destino,
            private_key_path=clave_privada, role=rol,
        ))
    return load_ssh_connections()


def remove_ssh(alias: str) -> list[dict]:
    with _conn() as conn:
        conn.execute(delete(t_ssh).where(t_ssh.c.alias == alias))
    return load_ssh_connections()


def get_ssh(alias: str) -> dict | None:
    for c in load_ssh_connections():
        if c["alias"] == alias:
            return c
    return None


def ssh_by_role(desired_role: str) -> list[dict]:
    return [
        c for c in load_ssh_connections()
        if c.get("rol") in (desired_role, "ambos")
    ]


# ─────────────────────────────────────────────────────────────────────────────
# WebDAV connections
# ─────────────────────────────────────────────────────────────────────────────

def load_webdav_connections() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(t_webdav)).mappings().all()
    return [
        {"letra": r["drive_letter"], "ip": r["ip"],
         "puerto": r["port"], "alias": r["alias"]}
        for r in rows
    ]


def add_or_update_webdav(letra: str, ip: str, puerto: str, alias: str = "") -> list[dict]:
    with _conn() as conn:
        conn.execute(delete(t_webdav).where(t_webdav.c.drive_letter == letra))
        conn.execute(insert(t_webdav).values(
            drive_letter=letra, ip=ip,
            port=puerto, alias=alias or letra,
        ))
    return load_webdav_connections()


def remove_webdav(letra: str) -> list[dict]:
    with _conn() as conn:
        conn.execute(delete(t_webdav).where(t_webdav.c.drive_letter == letra))
    return load_webdav_connections()


# ─────────────────────────────────────────────────────────────────────────────
# Source folders
# ─────────────────────────────────────────────────────────────────────────────

def load_source_folders() -> list[str]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(t_folders)).mappings().all()
    return [r["path"] for r in rows]


def save_source_folders(paths: list[str]) -> None:
    with _conn() as conn:
        conn.execute(delete(t_folders))
        for p in paths:
            conn.execute(insert(t_folders).values(path=p))


# ─────────────────────────────────────────────────────────────────────────────
# Destination config
# ─────────────────────────────────────────────────────────────────────────────

def load_destination_config() -> dict:
    with get_engine().connect() as conn:
        row = conn.execute(
            select(t_destination).where(t_destination.c.id == 1)
        ).mappings().first()
    if not row:
        return {}
    tipo = row["type"]
    if tipo == "local":
        return {"tipo": "local", "ruta": row["path"] or ""}
    if tipo == "ssh":
        return {"tipo": "ssh", "alias": row["ssh_alias"] or ""}
    return {}


def save_destination_local(ruta: str) -> None:
    with _conn() as conn:
        conn.execute(delete(t_destination))
        conn.execute(insert(t_destination).values(
            id=1, type="local", path=ruta, ssh_alias=None,
        ))


def save_destination_ssh(alias: str) -> None:
    with _conn() as conn:
        conn.execute(delete(t_destination))
        conn.execute(insert(t_destination).values(
            id=1, type="ssh", path=None, ssh_alias=alias,
        ))


def clear_destination() -> None:
    with _conn() as conn:
        conn.execute(delete(t_destination))


def load_saved_destination() -> str | None:
    cfg = load_destination_config()
    if cfg.get("tipo") == "local":
        return cfg.get("ruta")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Captures
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_capture_dict(r) -> dict:
    return {
        "id":              r["id"],
        "archivo":         r["filename"],
        "formato":         r["extension"],
        "tamano_mb":       r["size_mb"],
        "mtime":           r["mtime"],
        "fecha_captura":   r["capture_date"],
        "ruta_original":   r["source_path"],
        "ruta_destino":    r["dest_path"],
        "ruta_zip":        r["zip_path"],
        "ssh_alias":       r["ssh_alias"],
        "ssh_ruta_remota": r["ssh_remote_path"],
        "gps_lat":         r["gps_lat"],
        "gps_lon":         r["gps_lon"],
        "city":            r["city"],
        "tags":            decode_tags(r["tags"]),
    }


def load_captures() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(t_captures)).mappings().all()
    return [_row_to_capture_dict(r) for r in rows]


def load_captures_for_day(
    date: str,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    """Return one stable page of captures for an effective capture day.

    Captures with a normalized ``capture_date`` are filtered, counted and
    paginated by SQL. Legacy rows without a usable date are the only rows
    inspected in Python because their day must be derived from ``mtime``.
    """
    from datetime import datetime

    trimmed_date = func.trim(t_captures.c.capture_date)
    has_capture_date = func.length(trimmed_date) >= 10
    capture_day = func.substr(trimmed_date, 1, 10)
    file_path = case(
        (t_captures.c.dest_path != "", t_captures.c.dest_path),
        else_=t_captures.c.source_path,
    ).label("file_path")
    has_file_path = file_path != ""
    normal_filter = has_capture_date & (capture_day == date) & has_file_path
    legacy_filter = (~has_capture_date) & has_file_path
    order_by = (
        func.lower(t_captures.c.filename),
        func.lower(file_path),
    )

    def as_capture(row) -> dict:
        capture = _row_to_capture_dict(row)
        capture["file_path"] = row["file_path"]
        capture["is_favourite"] = bool(row["is_favourite"])
        return capture

    with get_engine().connect() as conn:
        normal_total = conn.execute(
            select(func.count()).select_from(t_captures).where(normal_filter)
        ).scalar_one()
        legacy_rows = conn.execute(
            select(t_captures, file_path).where(legacy_filter)
        ).mappings().all()

        matching_legacy = []
        for row in legacy_rows:
            photo_day = ""
            try:
                photo_day = datetime.fromtimestamp(float(row["mtime"])).strftime(
                    "%Y-%m-%d"
                )
            except (TypeError, ValueError, OSError, OverflowError):
                pass
            if (photo_day or "undated") == date:
                matching_legacy.append(as_capture(row))

        normal_query = select(t_captures, file_path).where(normal_filter)
        if matching_legacy:
            # Fetching the prefix is sufficient to merge a tiny legacy stream
            # without reading every capture belonging to this day.
            normal_rows = conn.execute(
                normal_query.order_by(*order_by).limit(offset + limit)
            ).mappings().all()
        else:
            normal_rows = conn.execute(
                normal_query.order_by(*order_by).offset(offset).limit(limit)
            ).mappings().all()

    normal_captures = [as_capture(row) for row in normal_rows]
    total = int(normal_total) + len(matching_legacy)
    if not matching_legacy:
        return normal_captures, total

    merged = normal_captures + matching_legacy
    merged.sort(key=lambda capture: (
        str(capture.get("archivo") or "").casefold(),
        str(capture["file_path"]).casefold(),
    ))
    return merged[offset:offset + limit], total


def upsert_captures(caps: list[dict]) -> None:
    """Bulk upsert captures from their to_dict() representation.

    capture_date is ALWAYS derived from the filename if possible.
    id is a proper UUID (cap_XXXX) — never a file path.
    """
    if not caps:
        return
    import uuid as _uuid

    from .utils.dates import extract_date_from_filename

    with _conn() as conn:
        for c in caps:
            # Derive real date from filename — this is the source of truth
            filename = c.get("archivo", "")
            filename_date = extract_date_from_filename(filename)
            cap_date = filename_date or c.get("fecha_captura", "")

            # Generate a stable id: if an existing row has this dest_path,
            # reuse its id (update). Otherwise generate a new UUID.
            dest = c.get("ruta_destino") or c.get("dest_path") or ""
            capture_id = c.get("id", "")

            # If id looks like a file path, replace it with a proper UUID
            if capture_id.startswith("/") or capture_id.startswith("C:") or \
               capture_id.startswith("\\"):
                # Check if a row already exists for this dest_path
                existing = conn.execute(
                    select(t_captures.c.id).where(t_captures.c.dest_path == dest)
                ).first()
                if existing:
                    capture_id = existing[0]
                else:
                    capture_id = f"cap_{_uuid.uuid4().hex[:12]}"
            elif not capture_id:
                capture_id = f"cap_{_uuid.uuid4().hex[:12]}"

            if dest:
                conn.execute(delete(t_captures).where(
                    (t_captures.c.id == capture_id) | (t_captures.c.dest_path == dest)
                ))
            else:
                conn.execute(delete(t_captures).where(t_captures.c.id == capture_id))
            conn.execute(insert(t_captures).values(
                id=capture_id,
                filename=filename,
                extension=c.get("formato", ""),
                size_mb=float(c.get("tamano_mb", 0)),
                mtime=float(c.get("mtime", 0)),
                capture_date=cap_date,
                source_path=c.get("ruta_original", ""),
                dest_path=dest,
                zip_path=c.get("ruta_zip"),
                ssh_alias=c.get("ssh_alias"),
                ssh_remote_path=c.get("ssh_ruta_remota"),
                gps_lat=c.get("gps_lat"),
                gps_lon=c.get("gps_lon"),
                city=c.get("city"),
                tags=encode_tags(c.get("tags", [])),
                is_favourite=False,
            ))


def get_capture_by_dest(dest_path: str) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            select(t_captures).where(t_captures.c.dest_path == dest_path)
        ).mappings().first()
    return _row_to_capture_dict(row) if row else None


def update_capture_zip(capture_id: str, zip_path: str) -> None:
    with _conn() as conn:
        conn.execute(
            update(t_captures)
            .where(t_captures.c.id == capture_id)
            .values(zip_path=zip_path)
        )


def update_capture_dest(capture_id: str, dest_path: str) -> None:
    with _conn() as conn:
        conn.execute(
            update(t_captures)
            .where(t_captures.c.id == capture_id)
            .values(dest_path=dest_path)
        )


def update_capture_gps_city(capture_id: str, gps_lat: float, gps_lon: float, city: str) -> None:
    with _conn() as conn:
        conn.execute(
            update(t_captures)
            .where(t_captures.c.id == capture_id)
            .values(gps_lat=gps_lat, gps_lon=gps_lon, city=city or None)
        )


def update_capture_tags(capture_id: str, tags: list) -> None:
    with _conn() as conn:
        conn.execute(
            update(t_captures)
            .where(t_captures.c.id == capture_id)
            .values(tags=encode_tags(tags))
        )


# ─────────────────────────────────────────────────────────────────────────────
# Favourites
# ─────────────────────────────────────────────────────────────────────────────

def load_favourites() -> list[str]:
    """Return dest_paths of all favourite captures."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(t_captures.c.dest_path)
            .where(t_captures.c.is_favourite == True)  # noqa: E712
            .where(t_captures.c.dest_path != None)     # noqa: E711
        ).all()
    return [r[0] for r in rows]


def set_favourite(path: str, flag: bool) -> None:
    with _conn() as conn:
        conn.execute(
            update(t_captures)
            .where(t_captures.c.dest_path == path)
            .values(is_favourite=flag)
        )


def bulk_set_favourite(paths: list[str], flag: bool) -> int:
    count = 0
    with _conn() as conn:
        for p in paths:
            result = conn.execute(
                update(t_captures)
                .where(t_captures.c.dest_path == p)
                .values(is_favourite=flag)
            )
            count += result.rowcount
    return count


def is_favourite(path: str) -> bool:
    with get_engine().connect() as conn:
        row = conn.execute(
            select(t_captures.c.is_favourite)
            .where(t_captures.c.dest_path == path)
        ).first()
    return bool(row[0]) if row else False


def favourites_set() -> set[str]:
    return set(load_favourites())


# ─────────────────────────────────────────────────────────────────────────────
# Albums
# ─────────────────────────────────────────────────────────────────────────────

def _album_photo_count(album_id: str, conn) -> int:
    row = conn.execute(
        select(t_album_photos)
        .where(t_album_photos.c.album_id == album_id)
    ).all()
    return len(row)


def load_albums() -> list[dict]:
    with get_engine().connect() as conn:
        albums = conn.execute(select(t_albums)).mappings().all()
        result = []
        for a in albums:
            photos = conn.execute(
                select(t_album_photos.c.photo_path)
                .where(t_album_photos.c.album_id == a["id"])
            ).all()
            photo_paths = [r[0] for r in photos]
            cover = a["cover"] or (photo_paths[0] if photo_paths else None)
            # fallback cover to first existing file
            if cover and not Path(cover).is_file():
                cover = next((p for p in photo_paths if Path(p).is_file()), cover)
            result.append({
                "id":       a["id"],
                "name":     a["name"],
                "cover":    cover,
                "created":  a["created_at"],
                "photos":   photo_paths,
                "count":    len(photo_paths),
            })
    return result


def get_album(album_id: str) -> dict | None:
    for a in load_albums():
        if a["id"] == album_id:
            return a
    return None


def create_album(album_id: str, name: str, created_at: str) -> dict:
    with _conn() as conn:
        conn.execute(insert(t_albums).values(
            id=album_id, name=name, cover=None, created_at=created_at,
        ))
    return {"id": album_id, "name": name, "cover": None,
            "created": created_at, "photos": [], "count": 0}


def update_album_name(album_id: str, name: str) -> None:
    with _conn() as conn:
        conn.execute(
            update(t_albums).where(t_albums.c.id == album_id).values(name=name)
        )


def update_album_cover(album_id: str, cover: str | None) -> None:
    with _conn() as conn:
        conn.execute(
            update(t_albums).where(t_albums.c.id == album_id).values(cover=cover)
        )


def delete_album(album_id: str) -> bool:
    with _conn() as conn:
        conn.execute(delete(t_album_photos).where(t_album_photos.c.album_id == album_id))
        result = conn.execute(delete(t_albums).where(t_albums.c.id == album_id))
    return result.rowcount > 0


def album_add_photos(album_id: str, paths: list[str]) -> int:
    with _conn() as conn:
        existing = {
            r[0] for r in conn.execute(
                select(t_album_photos.c.photo_path)
                .where(t_album_photos.c.album_id == album_id)
            ).all()
        }
        for p in paths:
            if p not in existing:
                conn.execute(insert(t_album_photos).values(
                    album_id=album_id, photo_path=p,
                ))
                existing.add(p)
        count = len(conn.execute(
            select(t_album_photos).where(t_album_photos.c.album_id == album_id)
        ).all())
    return count


def album_remove_photos(album_id: str, paths: list[str]) -> int:
    remove_set = set(paths)
    with _conn() as conn:
        for p in remove_set:
            conn.execute(
                delete(t_album_photos)
                .where(t_album_photos.c.album_id == album_id)
                .where(t_album_photos.c.photo_path == p)
            )
        # Clear cover if it was removed
        album = conn.execute(
            select(t_albums.c.cover).where(t_albums.c.id == album_id)
        ).first()
        if album and album[0] in remove_set:
            conn.execute(
                update(t_albums).where(t_albums.c.id == album_id).values(cover=None)
            )
        count = len(conn.execute(
            select(t_album_photos).where(t_album_photos.c.album_id == album_id)
        ).all())
    return count


def album_photo_paths(album_id: str) -> list[str]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(t_album_photos.c.photo_path)
            .where(t_album_photos.c.album_id == album_id)
        ).all()
    return [r[0] for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Day summaries
# ─────────────────────────────────────────────────────────────────────────────

def load_summaries() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(t_summaries)).mappings().all()
    return [
        {
            "fecha":           r["date"],
            "anio":            r["year"],
            "mes":             r["month"],
            "dia":             r["day"],
            "cantidad_fotos":  r["photo_count"],
            "tamano_total_mb": r["total_mb"],
            "destino":         r["dest_folder"],
            "ruta_zip":        r["zip_path"],
        }
        for r in rows
    ]


def upsert_summary(s: dict) -> None:
    with _conn() as conn:
        conn.execute(delete(t_summaries).where(t_summaries.c.date == s["fecha"]))
        conn.execute(insert(t_summaries).values(
            date=s["fecha"],
            year=s.get("anio"),
            month=s.get("mes"),
            day=s.get("dia"),
            photo_count=s.get("cantidad_fotos", 0),
            total_mb=s.get("tamano_total_mb", 0.0),
            dest_folder=s.get("destino"),
            zip_path=s.get("ruta_zip"),
        ))


def upsert_summaries(summaries: list[dict]) -> None:
    for s in summaries:
        upsert_summary(s)


# ─────────────────────────────────────────────────────────────────────────────
# Tags and Cities (computed views over captures)
# ─────────────────────────────────────────────────────────────────────────────

def load_all_tags() -> list[dict]:
    """All distinct tags with counts."""
    tag_counts: dict[str, int] = {}
    with get_engine().connect() as conn:
        rows = conn.execute(select(t_captures.c.tags)).all()
    for row in rows:
        for tag in decode_tags(row[0]):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return sorted(
        [{"tag": t, "count": c} for t, c in tag_counts.items()],
        key=lambda x: -x["count"],
    )


def load_all_cities() -> list[dict]:
    """All distinct cities with counts and cover paths."""
    city_data: dict[str, dict] = {}
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                t_captures.c.city,
                t_captures.c.dest_path,
                t_captures.c.gps_lat,
                t_captures.c.gps_lon,
            ).where(t_captures.c.city != None)  # noqa: E711
        ).all()
    for r in rows:
        city = (r[0] or "").strip()
        if not city:
            continue
        fpath = r[1]
        if city not in city_data:
            city_data[city] = {
                "city":  city,
                "count": 0,
                "cover": fpath if fpath and Path(fpath).is_file() else None,
                "lat":   r[2],
                "lon":   r[3],
            }
        city_data[city]["count"] += 1
        if city_data[city]["cover"] is None and fpath and Path(fpath).is_file():
            city_data[city]["cover"] = fpath
    return sorted(city_data.values(), key=lambda x: -x["count"])


def photos_by_city(city: str) -> list[dict]:
    """All captures for a given city, as photo dicts."""
    favs = favourites_set()
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(t_captures)
            .where(t_captures.c.city == city)
            .where(t_captures.c.dest_path != None)  # noqa: E711
        ).mappings().all()
    from urllib.parse import quote
    photos = []
    for r in rows:
        fpath = r["dest_path"]
        if not fpath or not Path(fpath).is_file():
            continue
        photos.append({
            "id":           fpath,
            "filename":     Path(fpath).name,
            "size_mb":      round(Path(fpath).stat().st_size / 1048576, 2),
            "capture_date": r["capture_date"],
            "tags":         decode_tags(r["tags"]),
            "city":         r["city"],
            "gps_lat":      r["gps_lat"],
            "gps_lon":      r["gps_lon"],
            "favourite":    fpath in favs,
            "url":          f"/api/photo?path={quote(fpath)}",
            "exists":       True,
        })
    return photos


# ═════════════════════════════════════════════════════════════════════════════
#  Users / authentication
# ═════════════════════════════════════════════════════════════════════════════

class AdminExistsError(Exception):
    """Raised when trying to create a second admin."""


class UsernameTakenError(Exception):
    """Raised when the username is already in use."""


def _row_to_user(r) -> dict:
    return {
        "id":         r["id"],
        "username":   r["username"],
        "role":       r["role"],
        "created_at": r["created_at"],
        "active":     bool(r["active"]),
    }


def admin_exists() -> bool:
    with get_engine().connect() as conn:
        row = conn.execute(
            select(t_users).where(t_users.c.role == "admin")
        ).first()
    return row is not None


def user_count() -> int:
    with get_engine().connect() as conn:
        return len(conn.execute(select(t_users.c.id)).all())


def get_user_by_username(username: str) -> dict | None:
    """Full row INCLUDING password_hash — for login verification only."""
    with get_engine().connect() as conn:
        row = conn.execute(
            select(t_users).where(t_users.c.username == username)
        ).mappings().first()
    if not row:
        return None
    d = _row_to_user(row)
    d["password_hash"] = row["password_hash"]
    return d


def get_user(user_id: str) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            select(t_users).where(t_users.c.id == user_id)
        ).mappings().first()
    return _row_to_user(row) if row else None


def create_user(username: str, password_hash: str, role: str = "user") -> dict:
    """Create a user. Enforces: unique username, and at most one admin.

    Raises AdminExistsError / UsernameTakenError on violation.
    """
    import uuid
    from datetime import datetime

    username = (username or "").strip()
    if not username:
        raise ValueError("Username cannot be empty")

    # Application-level guards (the DB partial index is the last line of defence)
    if get_user_by_username(username):
        raise UsernameTakenError(f"Username '{username}' is already taken")
    if role == "admin" and admin_exists():
        raise AdminExistsError("An administrator already exists")

    user_id = f"usr_{uuid.uuid4().hex[:10]}"
    created = datetime.now().isoformat(timespec="seconds")
    try:
        with _conn() as conn:
            conn.execute(insert(t_users).values(
                id=user_id, username=username, password_hash=password_hash,
                role=role, created_at=created, active=True,
            ))
    except Exception as e:
        # DB-level partial unique index rejected a second admin (race condition)
        msg = str(e).lower()
        if "ux_users_single_admin" in msg or "unique" in msg and role == "admin":
            raise AdminExistsError("An administrator already exists")
        if "unique" in msg:
            raise UsernameTakenError(f"Username '{username}' is already taken")
        raise
    return {"id": user_id, "username": username, "role": role,
            "created_at": created, "active": True}


def list_users() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(t_users).order_by(t_users.c.created_at)
        ).mappings().all()
    return [_row_to_user(r) for r in rows]


def delete_user(user_id: str) -> bool:
    with _conn() as conn:
        result = conn.execute(delete(t_users).where(t_users.c.id == user_id))
    return result.rowcount > 0


def set_user_password(user_id: str, password_hash: str) -> None:
    with _conn() as conn:
        conn.execute(
            update(t_users)
            .where(t_users.c.id == user_id)
            .values(password_hash=password_hash)
        )


def count_admins() -> int:
    with get_engine().connect() as conn:
        return len(conn.execute(
            select(t_users.c.id).where(t_users.c.role == "admin")
        ).all())


# ═════════════════════════════════════════════════════════════════════════════
#  Trash (soft-deleted photos)
# ═════════════════════════════════════════════════════════════════════════════

def add_to_trash(original_path: str, trash_path: str, filename: str,
                 size_mb: float) -> dict:
    """Record a photo that has been moved to the trash folder."""
    import uuid
    from datetime import datetime
    entry_id = f"trash_{uuid.uuid4().hex[:12]}"
    deleted_at = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        conn.execute(insert(t_trash).values(
            id=entry_id, original_path=original_path, trash_path=trash_path,
            filename=filename, size_mb=size_mb, deleted_at=deleted_at,
        ))
    return {"id": entry_id, "original_path": original_path,
            "trash_path": trash_path, "filename": filename,
            "size_mb": size_mb, "deleted_at": deleted_at}


def list_trash() -> list[dict]:
    """All trashed photos, newest first."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(t_trash).order_by(t_trash.c.deleted_at.desc())
        ).mappings().all()
    return [
        {
            "id":            r["id"],
            "original_path": r["original_path"],
            "trash_path":    r["trash_path"],
            "filename":      r["filename"],
            "size_mb":       r["size_mb"],
            "deleted_at":    r["deleted_at"],
        }
        for r in rows
    ]


def get_trash_entry(entry_id: str) -> dict | None:
    with get_engine().connect() as conn:
        r = conn.execute(
            select(t_trash).where(t_trash.c.id == entry_id)
        ).mappings().first()
    if not r:
        return None
    return {
        "id":            r["id"],
        "original_path": r["original_path"],
        "trash_path":    r["trash_path"],
        "filename":      r["filename"],
        "size_mb":       r["size_mb"],
        "deleted_at":    r["deleted_at"],
    }


def remove_trash_entry(entry_id: str) -> bool:
    with _conn() as conn:
        result = conn.execute(delete(t_trash).where(t_trash.c.id == entry_id))
    return result.rowcount > 0


def trash_entries_older_than(days: int) -> list[dict]:
    """Return trash entries deleted more than `days` days ago."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(t_trash).where(t_trash.c.deleted_at < cutoff)
        ).mappings().all()
    return [dict(r) for r in rows]


def trash_count() -> int:
    with get_engine().connect() as conn:
        return len(conn.execute(select(t_trash.c.id)).all())
