-- Reproducible PostgreSQL benchmark. The table is temporary and disappears
-- when psql exits, so this script never changes application data.
\timing on

CREATE TEMP TABLE captures_benchmark AS
SELECT
    'cap_' || n AS id,
    'IMG_' || lpad(n::text, 9, '0') || '.jpg' AS filename,
    (
        timestamp '2018-01-01 00:00:00'
        + ((n * 37) % 3287) * interval '1 day'
        + (n % 86400) * interval '1 second'
    )::text AS capture_date,
    NULL::date AS capture_day,
    '/source/' || n || '.jpg' AS source_path,
    '/photos/' || n || '.jpg' AS dest_path,
    (n % 20 = 0) AS is_favourite
FROM generate_series(1, 200000) AS series(n);

ANALYZE captures_benchmark;

\echo Legacy day lookup
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, filename
FROM captures_benchmark
WHERE substr(btrim(capture_date), 1, 10) = '2024-06-15'
ORDER BY lower(filename)
LIMIT 60;

\echo Legacy global first page
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, filename
FROM captures_benchmark
WHERE length(btrim(capture_date)) >= 10
ORDER BY substr(btrim(capture_date), 1, 10) DESC, lower(filename)
LIMIT 60;

\echo Backfill and index build
UPDATE captures_benchmark
SET capture_day = capture_date::timestamp::date;

CREATE INDEX ix_benchmark_capture_day
    ON captures_benchmark (capture_day DESC);
CREATE INDEX ix_benchmark_favourite_day
    ON captures_benchmark (is_favourite, capture_day DESC);
ANALYZE captures_benchmark;

\echo Indexed day lookup
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, filename
FROM captures_benchmark
WHERE capture_day = date '2024-06-15'
ORDER BY lower(filename)
LIMIT 60;

\echo Indexed global first page
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, filename
FROM captures_benchmark
WHERE capture_day IS NOT NULL
ORDER BY capture_day DESC, lower(filename)
LIMIT 60;
