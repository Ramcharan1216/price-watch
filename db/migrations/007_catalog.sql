-- Phones and brands the system has discovered, and when each background job last ran
CREATE TABLE IF NOT EXISTS catalog_models (
    brand       TEXT NOT NULL,
    model       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'proposed',     -- proposed | approved | rejected
    title_keys  JSONB NOT NULL DEFAULT '[]',          -- distinct listings that showed this model
    merchants   JSONB NOT NULL DEFAULT '[]',          -- distinct stores that showed it
    example     TEXT,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_by  TEXT,                                 -- auto | manual
    PRIMARY KEY (brand, model)
);
CREATE TABLE IF NOT EXISTS job_state (
    name     TEXT PRIMARY KEY,
    last_run TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail   TEXT
);
