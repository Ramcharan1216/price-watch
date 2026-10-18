"""Shared helpers for every ingestion job.

Storage rule: a price row is saved only when the price CHANGED since the last
one we stored. Unchanged prices just update listings.last_checked. The price on
any day is the latest row on or before that day, so no history is lost.
"""
import os
from datetime import datetime, timezone
from decimal import Decimal

import psycopg
from dotenv import load_dotenv

load_dotenv()


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"])


def get_store_id(conn, slug):
    row = conn.execute("SELECT id FROM stores WHERE slug = %s", (slug,)).fetchone()
    if not row:
        raise ValueError(f"Unknown store '{slug}'. Add it to the stores table first.")
    return row[0]


def start_run(conn, store_id):
    run_id = conn.execute(
        "INSERT INTO ingestion_runs (store_id) VALUES (%s) RETURNING id", (store_id,)
    ).fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id, status, rows_loaded=0, error=None):
    conn.execute(
        "UPDATE ingestion_runs SET finished_at = now(), status = %s, "
        "rows_loaded = %s, error_message = %s WHERE id = %s",
        (status, rows_loaded, error, run_id),
    )
    conn.commit()


def now_utc():
    return datetime.now(timezone.utc)


def _money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def load_observations(conn, store_id, run_id, observed_at, rows):
    """rows: dicts with store_sku, raw_title, price_inr, optional url, in_stock.
    Returns (changed, unchanged): new price rows stored vs. prices left as-is."""
    changed = unchanged = 0
    for r in rows:
        listing_id = conn.execute(
            """INSERT INTO listings (store_id, store_sku, url, raw_title, last_seen, last_checked)
               VALUES (%s, %s, %s, %s, now(), now())
               ON CONFLICT (store_id, store_sku) DO UPDATE
                 SET last_seen = now(),
                     last_checked = now(),
                     raw_title = EXCLUDED.raw_title,
                     url = COALESCE(EXCLUDED.url, listings.url)
               RETURNING id""",
            (store_id, r["store_sku"], r.get("url"), r["raw_title"]),
        ).fetchone()[0]

        obs = r.get("observed_at") or observed_at
        # Compare with the price AS OF this observation time, so replaying or
        # backfilling history never creates duplicate or out-of-order rows.
        last = conn.execute(
            "SELECT price_inr FROM price_history WHERE listing_id = %s "
            "AND observed_at <= %s ORDER BY observed_at DESC LIMIT 1",
            (listing_id, obs),
        ).fetchone()
        new_price = _money(r["price_inr"])

        if last is not None and _money(last[0]) == new_price:
            unchanged += 1
            continue

        conn.execute(
            """INSERT INTO price_history (listing_id, observed_at, price_inr, in_stock, run_id)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (listing_id, observed_at) DO UPDATE
                 SET price_inr = EXCLUDED.price_inr, in_stock = EXCLUDED.in_stock""",
            (listing_id, obs, new_price, r.get("in_stock"), run_id),
        )
        changed += 1
    return changed, unchanged
