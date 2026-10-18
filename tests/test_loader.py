"""Checks the change-only storage rule. Uses its own throwaway store and cleans up.
Run from the project folder:  python tests/test_loader.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion"))
from common import connect, load_observations, now_utc, start_run  # noqa: E402

SLUG = "test_store"


def rows(prices):
    return [{"store_sku": f"T{i}", "raw_title": f"Test phone {i}", "price_inr": p}
            for i, p in enumerate(prices)]


def stored(conn, sid):
    return conn.execute(
        "SELECT count(*) FROM price_history p JOIN listings l ON l.id = p.listing_id "
        "WHERE l.store_id = %s", (sid,)).fetchone()[0]


def cleanup(conn, sid):
    conn.execute("DELETE FROM price_history WHERE listing_id IN "
                 "(SELECT id FROM listings WHERE store_id = %s)", (sid,))
    conn.execute("DELETE FROM listings WHERE store_id = %s", (sid,))
    conn.execute("DELETE FROM ingestion_runs WHERE store_id = %s", (sid,))
    conn.execute("DELETE FROM stores WHERE id = %s", (sid,))
    conn.commit()


conn = connect()
sid = conn.execute("INSERT INTO stores (slug, name) VALUES (%s, 'Test') "
                   "ON CONFLICT (slug) DO UPDATE SET name = 'Test' RETURNING id", (SLUG,)).fetchone()[0]
conn.commit()
try:
    run = start_run(conn, sid)

    c, u = load_observations(conn, sid, run, now_utc(), rows([1000, 2000, 3000]))
    assert (c, u) == (3, 0), f"first load should store 3, got {(c, u)}"

    c, u = load_observations(conn, sid, run, now_utc(), rows([1000, 2000, 3000]))
    assert (c, u) == (0, 3), f"same prices should store 0, got {(c, u)}"

    c, u = load_observations(conn, sid, run, now_utc(), rows([1000, 1800, 3000]))
    assert (c, u) == (1, 2), f"one change should store 1, got {(c, u)}"
    conn.commit()

    assert stored(conn, sid) == 4, "expected 4 stored rows in total"
    latest = conn.execute(
        "SELECT p.price_inr FROM price_history p JOIN listings l ON l.id = p.listing_id "
        "WHERE l.store_id = %s AND l.store_sku = 'T1' ORDER BY p.observed_at DESC LIMIT 1",
        (sid,)).fetchone()[0]
    assert float(latest) == 1800.0, "latest price for T1 should be 1800"
    checked = conn.execute("SELECT count(*) FROM listings WHERE store_id = %s "
                           "AND last_checked IS NOT NULL", (sid,)).fetchone()[0]
    assert checked == 3, "all listings should have last_checked set"
    print("PASS: only changed prices are stored, unchanged ones are skipped")

    # --- history replay: loading the same dated rows twice must add nothing ---
    from datetime import datetime, timezone, timedelta
    d0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hist = []
    for day, price in enumerate([500, 500, 520, 520, 520, 480]):
        hist.append({"store_sku": "H1", "raw_title": "History phone", "price_inr": price,
                     "observed_at": d0 + timedelta(days=day)})
    c, u = load_observations(conn, sid, run, now_utc(), hist)
    assert (c, u) == (3, 3), f"history should store 3 changes, got {(c, u)}"
    c, u = load_observations(conn, sid, run, now_utc(), hist)
    assert (c, u) == (0, 6), f"replaying history should store 0, got {(c, u)}"
    conn.commit()
    print("PASS: replaying a history file adds no duplicate rows")
finally:
    conn.rollback()
    cleanup(conn, sid)
