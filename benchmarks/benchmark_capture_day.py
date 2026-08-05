"""Compare legacy text-date queries with indexed capture_day queries.

This benchmark uses only sqlite3 so it is reproducible without touching the
application database. It models the two gallery query shapes and reports the
one-time migration/index build cost. PostgreSQL timings will differ, but the
query-plan distinction (full scan versus indexed lookup) remains the same.
"""
from __future__ import annotations

import argparse
import random
import sqlite3
import statistics
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path


def timed(connection: sqlite3.Connection, sql: str, params: tuple, repeats: int) -> list[float]:
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        connection.execute(sql, params).fetchall()
        samples.append((time.perf_counter() - started) * 1_000)
    return samples


def summarize(samples: list[float]) -> str:
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return f"median={statistics.median(samples):8.3f} ms  p95={p95:8.3f} ms"


def plan(connection: sqlite3.Connection, sql: str, params: tuple) -> str:
    rows = connection.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    return " | ".join(str(row[3]) for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    random.seed(args.seed)
    with tempfile.TemporaryDirectory(prefix="photos-sync-benchmark-") as temp_dir:
        database = Path(temp_dir) / "benchmark.sqlite3"
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute(
            """
            CREATE TABLE captures (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                capture_date TEXT,
                capture_day DATE,
                source_path TEXT NOT NULL,
                dest_path TEXT,
                is_favourite INTEGER NOT NULL
            )
            """
        )

        first_day = date(2018, 1, 1)
        day_span = (date(2026, 12, 31) - first_day).days
        batch = []
        insert_started = time.perf_counter()
        for index in range(args.rows):
            capture_day = first_day + timedelta(days=random.randrange(day_span))
            capture_time = datetime.combine(capture_day, datetime.min.time()).replace(
                hour=random.randrange(24), minute=random.randrange(60), second=random.randrange(60)
            )
            batch.append((
                f"cap_{index:09d}",
                f"IMG_{index:09d}.jpg",
                capture_time.isoformat(sep=" "),
                None,
                f"/source/{index:09d}.jpg",
                f"/photos/{capture_day:%Y/%m/%d}/{index:09d}.jpg",
                1 if index % 20 == 0 else 0,
            ))
            if len(batch) == 10_000:
                connection.executemany("INSERT INTO captures VALUES (?,?,?,?,?,?,?)", batch)
                batch.clear()
        if batch:
            connection.executemany("INSERT INTO captures VALUES (?,?,?,?,?,?,?)", batch)
        connection.commit()
        insert_seconds = time.perf_counter() - insert_started

        target = "2024-06-15"
        legacy_day = """
            SELECT id, filename
            FROM captures
            WHERE substr(trim(capture_date), 1, 10) = ?
            ORDER BY lower(filename)
            LIMIT 60
        """
        legacy_global = """
            SELECT id, filename
            FROM captures
            WHERE length(trim(capture_date)) >= 10
            ORDER BY substr(trim(capture_date), 1, 10) DESC, lower(filename)
            LIMIT 60
        """

        # Warm caches before collecting legacy samples.
        connection.execute(legacy_day, (target,)).fetchall()
        connection.execute(legacy_global).fetchall()
        legacy_day_samples = timed(connection, legacy_day, (target,), args.repeats)
        legacy_global_samples = timed(connection, legacy_global, (), args.repeats)

        migration_started = time.perf_counter()
        connection.execute("UPDATE captures SET capture_day = substr(capture_date, 1, 10)")
        connection.execute(
            "CREATE INDEX ix_captures_capture_day ON captures(capture_day DESC)"
        )
        connection.execute(
            "CREATE INDEX ix_captures_favourite_day "
            "ON captures(is_favourite, capture_day DESC)"
        )
        connection.commit()
        migration_seconds = time.perf_counter() - migration_started

        indexed_day = """
            SELECT id, filename
            FROM captures
            WHERE capture_day = ?
            ORDER BY lower(filename)
            LIMIT 60
        """
        indexed_global = """
            SELECT id, filename
            FROM captures
            WHERE capture_day IS NOT NULL
            ORDER BY capture_day DESC, lower(filename)
            LIMIT 60
        """
        connection.execute(indexed_day, (target,)).fetchall()
        connection.execute(indexed_global).fetchall()
        indexed_day_samples = timed(connection, indexed_day, (target,), args.repeats)
        indexed_global_samples = timed(connection, indexed_global, (), args.repeats)

        print(f"Rows: {args.rows:,}")
        print(f"Fixture creation: {insert_seconds:.3f} s")
        print(f"Migration + two indexes: {migration_seconds:.3f} s")
        print()
        print("Day lookup")
        print(f"  legacy : {summarize(legacy_day_samples)}")
        print(f"  indexed: {summarize(indexed_day_samples)}")
        print(f"  speedup: {statistics.median(legacy_day_samples) / statistics.median(indexed_day_samples):.1f}x")
        print(f"  legacy plan : {plan(connection, legacy_day, (target,))}")
        print(f"  indexed plan: {plan(connection, indexed_day, (target,))}")
        print()
        print("Global first page")
        print(f"  legacy : {summarize(legacy_global_samples)}")
        print(f"  indexed: {summarize(indexed_global_samples)}")
        print(f"  speedup: {statistics.median(legacy_global_samples) / statistics.median(indexed_global_samples):.1f}x")
        print(f"  legacy plan : {plan(connection, legacy_global, ())}")
        print(f"  indexed plan: {plan(connection, indexed_global, ())}")
        connection.close()


if __name__ == "__main__":
    main()
