-- Phase 0 schema. Runs once, when the database volume is first created.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE stores (
    id          SMALLSERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    data_source TEXT NOT NULL DEFAULT 'undecided'  -- api | affiliate | scrape | dataset
);

-- One row per real-world product (a specific phone variant).
CREATE TABLE products (
    id             BIGSERIAL PRIMARY KEY,
    category       TEXT NOT NULL DEFAULT 'smartphone',
    brand          TEXT NOT NULL,
    model          TEXT NOT NULL,
    ram_gb         SMALLINT,
    storage_gb     INTEGER,
    gtin           TEXT UNIQUE,
    canonical_name TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (brand, model, ram_gb, storage_gb)
);
CREATE INDEX products_name_trgm ON products USING gin (canonical_name gin_trgm_ops);

-- One row per store listing. Matched to a product in Phase 2.
CREATE TABLE listings (
    id               BIGSERIAL PRIMARY KEY,
    store_id         SMALLINT NOT NULL REFERENCES stores(id),
    store_sku        TEXT NOT NULL,
    url              TEXT,
    raw_title        TEXT NOT NULL,
    product_id       BIGINT REFERENCES products(id),
    match_confidence REAL,
    match_status     TEXT NOT NULL DEFAULT 'unmatched',  -- unmatched | auto | review | manual
    first_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (store_id, store_sku)
);
CREATE INDEX listings_product_idx ON listings (product_id);
CREATE INDEX listings_title_trgm ON listings USING gin (raw_title gin_trgm_ops);

CREATE TABLE ingestion_runs (
    id            BIGSERIAL PRIMARY KEY,
    store_id      SMALLINT REFERENCES stores(id),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running',  -- running | success | failed
    rows_loaded   INTEGER DEFAULT 0,
    error_message TEXT
);

-- Raw responses are kept untouched so you can re-parse later.
CREATE TABLE raw_responses (
    id          BIGSERIAL PRIMARY KEY,
    run_id      BIGINT REFERENCES ingestion_runs(id),
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_url  TEXT,
    payload     JSONB NOT NULL
);

-- Time series: one row per listing per observation.
CREATE TABLE price_history (
    listing_id  BIGINT NOT NULL REFERENCES listings(id),
    observed_at TIMESTAMPTZ NOT NULL,
    price_inr   NUMERIC(12,2) NOT NULL CHECK (price_inr > 0),
    in_stock    BOOLEAN,
    run_id      BIGINT REFERENCES ingestion_runs(id),
    PRIMARY KEY (listing_id, observed_at)
);

-- Used in Phase 6 (DRAM trend, USD-INR, news, search trends, launches).
CREATE TABLE signals (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,
    category    TEXT,
    observed_on DATE NOT NULL,
    value       NUMERIC,
    detail      JSONB,
    source      TEXT NOT NULL,
    UNIQUE (kind, category, observed_on, source)
);

-- Placeholder stores. Edit after you decide your sources (see docs/spec.md).
INSERT INTO stores (slug, name) VALUES
    ('amazon_in', 'Amazon India'),
    ('flipkart', 'Flipkart'),
    ('croma', 'Croma')
ON CONFLICT DO NOTHING;
