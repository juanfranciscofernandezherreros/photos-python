"""Compare the former row-at-a-time persistence with the bulk upsert."""
from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from sqlalchemy import delete, insert

from photos_sync import db, repository


def records(count: int) -> list[dict]:
    return [{
        "id": f"cap_{index:09d}",
        "archivo": f"IMG_20240101_{index % 24:02d}{index % 60:02d}00.jpg",
        "formato": "jpg",
        "tamano_mb": 1.25,
        "mtime": 1_704_067_200 + index,
        "fecha_captura": "2024-01-01T00:00:00",
        "ruta_original": f"/source/{index}.jpg",
        "ruta_destino": f"/photos/{index}.jpg",
        "tags": [],
    } for index in range(count)]


def legacy_insert(engine, captures: list[dict]) -> float:
    started = time.perf_counter()
    with engine.begin() as connection:
        for capture in captures:
            connection.execute(
                delete(db.t_captures).where(db.t_captures.c.id == capture["id"])
            )
            connection.execute(insert(db.t_captures).values(
                id=capture["id"],
                filename=capture["archivo"],
                extension=capture["formato"],
                size_mb=capture["tamano_mb"],
                mtime=capture["mtime"],
                capture_date=None,
                capture_day=None,
                source_path=capture["ruta_original"],
                dest_path=capture["ruta_destino"],
                tags="[]",
                is_favourite=False,
            ))
    return time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=5_000)
    args = parser.parse_args()
    captures = records(args.rows)

    with tempfile.TemporaryDirectory(prefix="photos-sync-upsert-") as temp:
        engine = db._create_engine_from_url(f"sqlite:///{Path(temp) / 'benchmark.sqlite3'}")
        db.init_db(engine)
        db.set_engine(engine)

        legacy_seconds = legacy_insert(engine, captures)
        with engine.begin() as connection:
            connection.execute(delete(db.t_captures))

        started = time.perf_counter()
        repository.upsert_captures(captures)
        bulk_seconds = time.perf_counter() - started

        print(f"Rows: {args.rows:,}")
        print(f"Legacy DELETE + INSERT: {legacy_seconds:.3f} s")
        print(f"Bulk upsert:            {bulk_seconds:.3f} s")
        print(f"Speedup:                {legacy_seconds / bulk_seconds:.1f}x")
        engine.dispose()
        db.set_engine(None)


if __name__ == "__main__":
    main()
