CREATE TABLE IF NOT EXISTS forecasts (
    product_id    BIGINT NOT NULL REFERENCES products(id),
    made_on       DATE NOT NULL,
    horizon_days  SMALLINT NOT NULL,
    current_price NUMERIC(12,2) NOT NULL,
    p10           NUMERIC(12,2) NOT NULL,
    p50           NUMERIC(12,2) NOT NULL,
    p90           NUMERIC(12,2) NOT NULL,
    naive_p10     NUMERIC(12,2) NOT NULL,
    naive_p90     NUMERIC(12,2) NOT NULL,
    model_version TEXT NOT NULL,
    PRIMARY KEY (product_id, made_on, horizon_days)
);
CREATE TABLE IF NOT EXISTS model_reports (
    id         BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    report     JSONB NOT NULL
);
