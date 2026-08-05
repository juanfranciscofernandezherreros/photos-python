from __future__ import annotations

from sqlalchemy import event, select


def _captures(count: int) -> list[dict]:
    return [{
        "id": f"cap_{index:06d}",
        "archivo": f"IMG_20240101_{index % 24:02d}{index % 60:02d}00.jpg",
        "formato": "jpg",
        "tamano_mb": 1.5,
        "mtime": 1_704_067_200 + index,
        "fecha_captura": "2024-01-01T00:00:00",
        "ruta_original": f"/source/{index}.jpg",
        "ruta_destino": f"/photos/{index}.jpg",
        "tags": ["camera"],
    } for index in range(count)]


def test_bulk_upsert_uses_bounded_statement_count(db_engine):
    from photos_sync import repository as repo

    captures = _captures(200)
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", record_statement)
    try:
        repo.upsert_captures(captures)
    finally:
        event.remove(db_engine, "before_cursor_execute", record_statement)

    # One destination lookup plus four 50-row SQLite upserts. The previous
    # implementation required at least 400 DELETE/INSERT statements.
    assert len(statements) <= 6
    assert len(repo.load_captures()) == 200


def test_resync_preserves_favourite_and_stable_id(db_engine):
    from photos_sync import repository as repo
    from photos_sync.db import t_captures

    capture = _captures(1)[0]
    repo.upsert_captures([capture])
    repo.set_favourite(capture["ruta_destino"], True)

    updated = dict(capture)
    updated.update({
        "id": capture["ruta_destino"],
        "tamano_mb": 2.0,
        "tags": ["camera", "updated"],
    })
    repo.upsert_captures([updated])

    with db_engine.connect() as connection:
        row = connection.execute(select(t_captures)).mappings().one()

    assert row["id"] == capture["id"]
    assert row["is_favourite"] is True
    assert row["size_mb"] == 2.0


def test_batch_deduplicates_repeated_destination(db_engine):
    from photos_sync import repository as repo

    first = _captures(1)[0]
    second = dict(first, id="another-id", tamano_mb=3.0)
    repo.upsert_captures([first, second])

    captures = repo.load_captures()
    assert len(captures) == 1
    assert captures[0]["tamano_mb"] == 3.0
