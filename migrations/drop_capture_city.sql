-- Run after deploying the application version that no longer reads or writes
-- captures.city. Back up the PostgreSQL database before applying this change.
ALTER TABLE captures DROP COLUMN IF EXISTS city;
