CREATE TABLE IF NOT EXISTS price_moves (
    product_id  BIGINT NOT NULL REFERENCES products(id),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    kind        TEXT NOT NULL,            -- sudden | gradual
    change_pct  NUMERIC(7,2) NOT NULL,
    start_price NUMERIC(12,2) NOT NULL,
    end_price   NUMERIC(12,2) NOT NULL,
    reasons     JSONB NOT NULL DEFAULT '[]',
    PRIMARY KEY (product_id, start_date, kind)
);
