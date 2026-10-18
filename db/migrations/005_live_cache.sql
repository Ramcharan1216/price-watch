-- Saved live-search answers (so the same question does not call the source again)
CREATE TABLE IF NOT EXISTS live_cache (
    query_key  TEXT PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source     TEXT NOT NULL,
    result     JSONB NOT NULL
);
-- How many times we called the price source each day (to stay inside its quota)
CREATE TABLE IF NOT EXISTS live_usage (
    day   DATE PRIMARY KEY,
    calls INTEGER NOT NULL DEFAULT 0
);
