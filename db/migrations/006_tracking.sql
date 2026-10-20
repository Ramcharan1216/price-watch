-- Searches worth keeping fresh, and where each saved price came from
CREATE TABLE IF NOT EXISTS tracked_queries (
    query_key      TEXT PRIMARY KEY,
    first_searched TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_searched  TIMESTAMPTZ NOT NULL DEFAULT now(),
    searches       INTEGER NOT NULL DEFAULT 1,
    last_refreshed TIMESTAMPTZ
);
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS source TEXT;
