-- PostgreSQL 16 migration for indexed photo dates.
--
-- Apply after taking a backup and before starting the application version
-- that maps captures.capture_date as TIMESTAMP and writes capture_day.
-- The ALTER TYPE takes a table lock; schedule a maintenance window for a
-- large captures table. Invalid legacy timestamps become NULL, while their
-- capture_day still falls back to mtime when possible.

BEGIN;

ALTER TABLE captures
    ADD COLUMN IF NOT EXISTS capture_day DATE;

UPDATE captures
SET capture_day = CASE
    WHEN capture_date IS NOT NULL
         AND btrim(capture_date::text) <> ''
         AND pg_input_is_valid(
             btrim(capture_date::text),
             'timestamp without time zone'
         )
        THEN btrim(capture_date::text)::timestamp::date
    WHEN mtime > 0
        THEN to_timestamp(mtime)::date
    ELSE NULL
END
WHERE capture_day IS NULL
  AND (
      (
          capture_date IS NOT NULL
          AND btrim(capture_date::text) <> ''
          AND pg_input_is_valid(
              btrim(capture_date::text),
              'timestamp without time zone'
          )
      )
      OR mtime > 0
  );

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'captures'
          AND column_name = 'capture_date'
          AND data_type IN ('text', 'character varying')
    ) THEN
        ALTER TABLE captures ALTER COLUMN capture_date DROP DEFAULT;
        ALTER TABLE captures ALTER COLUMN capture_date DROP NOT NULL;
        ALTER TABLE captures
            ALTER COLUMN capture_date TYPE TIMESTAMP WITHOUT TIME ZONE
            USING CASE
                WHEN capture_date IS NOT NULL
                     AND btrim(capture_date) <> ''
                     AND pg_input_is_valid(
                         btrim(capture_date),
                         'timestamp without time zone'
                     )
                    THEN btrim(capture_date)::timestamp
                ELSE NULL
            END;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_captures_dest_path
    ON captures (dest_path)
    WHERE dest_path IS NOT NULL AND dest_path <> '';

CREATE INDEX IF NOT EXISTS ix_captures_source_path
    ON captures (source_path);

CREATE INDEX IF NOT EXISTS ix_captures_capture_day
    ON captures (capture_day DESC);

CREATE INDEX IF NOT EXISTS ix_captures_favourite_day
    ON captures (is_favourite, capture_day DESC);

CREATE UNIQUE INDEX IF NOT EXISTS ux_album_photos_album_path
    ON album_photos (album_id, photo_path);

CREATE INDEX IF NOT EXISTS ix_album_photos_photo_path
    ON album_photos (photo_path);

CREATE INDEX IF NOT EXISTS ix_trash_deleted_at
    ON trash (deleted_at);

ANALYZE captures;
ANALYZE album_photos;
ANALYZE trash;

COMMIT;
