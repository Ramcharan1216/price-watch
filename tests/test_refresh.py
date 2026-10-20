"""Scheduled refresh checks (needs the database).   python tests/test_refresh.py
Uses a throwaway store and phone, and removes everything it created."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from live.adapters.base import BaseAdapter  # noqa: E402
from live.pipeline import live_search, refresh_queries  # noqa: E402

STORE, KEY = "refreshtest_store", "zzrefresh galaxy"


class Shop(BaseAdapter):
    name = "test shop"

    def __init__(self, price):
        self.price, self.calls = price, 0

    def search(self, query):
        self.calls += 1
        return [{"store": STORE, "store_name": "Test Store", "sku": "R1", "origin": "test",
                 "title": "Samsung Galaxy S24 5G (Onyx Black, 12GB RAM, 1024GB Storage)", "price_inr": self.price, "url": "https://x/r1"}]


conn = psycopg.connect(os.environ["DATABASE_URL"])
before = (conn.execute("SELECT calls FROM live_usage WHERE day = current_date").fetchone() or [0])[0]


def prices():
    return [float(r[0]) for r in conn.execute(
        "SELECT p.price_inr FROM price_history p JOIN listings l ON l.id = p.listing_id JOIN stores s ON s.id = l.store_id "
        "WHERE s.slug = %s ORDER BY p.observed_at", (STORE,))]


def cleanup():
    conn.rollback()
    ids = [r[0] for r in conn.execute("SELECT l.id FROM listings l JOIN stores s ON s.id = l.store_id WHERE s.slug = %s", (STORE,))]
    pids = {r[0] for r in conn.execute("SELECT DISTINCT product_id FROM listings WHERE id = ANY(%s) AND product_id IS NOT NULL", (ids,))}
    conn.execute("DELETE FROM price_history WHERE listing_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM listings WHERE id = ANY(%s)", (ids,))
    for pid in pids:
        if not conn.execute("SELECT 1 FROM listings WHERE product_id = %s LIMIT 1", (pid,)).fetchone():
            conn.execute("DELETE FROM forecasts WHERE product_id = %s", (pid,))
            conn.execute("DELETE FROM price_moves WHERE product_id = %s", (pid,))
            conn.execute("DELETE FROM products WHERE id = %s", (pid,))
    conn.execute("DELETE FROM ingestion_runs WHERE store_id IS NULL OR store_id IN (SELECT id FROM stores WHERE slug = %s)", (STORE,))
    conn.execute("DELETE FROM stores WHERE slug = %s", (STORE,))
    conn.execute("DELETE FROM tracked_queries WHERE query_key LIKE 'zz%'")
    conn.execute("DELETE FROM live_cache WHERE query_key LIKE 'zz%'")
    conn.execute("INSERT INTO live_usage (day, calls) VALUES (current_date, %s) ON CONFLICT (day) DO UPDATE SET calls = %s", (before, before))
    conn.commit()


def tracked():
    return conn.execute("SELECT searches, last_refreshed FROM tracked_queries WHERE query_key = %s", (KEY,)).fetchone()


try:
    cleanup()
    shop = Shop(99999)
    # 1. a search that found something is remembered, and counted again when repeated
    live_search(KEY, adapter=shop)
    assert tracked() == (1, None), tracked()
    live_search(KEY, adapter=shop)                      # answered from the saved copy
    assert tracked()[0] == 2 and shop.calls == 1, "repeat searches raise demand but do not call the source"
    assert prices() == [99999.0] and conn.execute("SELECT source FROM price_history ph JOIN listings l ON l.id = ph.listing_id JOIN stores s ON s.id = l.store_id WHERE s.slug = %s", (STORE,)).fetchone()[0] == "test"

    # 2. the refresh asks the source again and saves only what changed
    shop.price = 94999
    r = refresh_queries(limit=5, stale_minutes=0, pause=0, adapter=shop)
    assert r["refreshed"] == 1 and r["new_prices_stored"] == 1 and shop.calls == 2, r
    assert prices() == [99999.0, 94999.0] and tracked()[1] is not None
    assert tracked()[0] == 2, "refreshing must not count as a search"

    # 3. nothing changed: a refresh stores nothing; recently refreshed searches are skipped
    assert refresh_queries(limit=5, stale_minutes=0, pause=0, adapter=shop)["new_prices_stored"] == 0
    calls = shop.calls
    assert refresh_queries(limit=5, stale_minutes=60, pause=0, adapter=shop)["checked"] == 0 and shop.calls == calls

    # 4. the daily limit stops the refresh cleanly
    conn.execute("INSERT INTO live_usage (day, calls) VALUES (current_date, 7) ON CONFLICT (day) DO UPDATE SET calls = 7")
    conn.commit()
    r = refresh_queries(limit=5, stale_minutes=0, pause=0, daily_cap=7, adapter=shop)
    assert r["refreshed"] == 0 and r["stopped"] and shop.calls == calls, r

    # 5. searches that found nothing are not tracked
    Empty = type("Empty", (BaseAdapter,), {"name": "empty source", "search": lambda self, q: []})
    live_search("zzrefresh nothing", adapter=Empty())
    assert conn.execute("SELECT 1 FROM tracked_queries WHERE query_key = 'zzrefresh nothing'").fetchone() is None
    print("PASS: searches are tracked, refreshed on a schedule without double-counting, store only changes, and stop at the daily limit")
finally:
    cleanup()
