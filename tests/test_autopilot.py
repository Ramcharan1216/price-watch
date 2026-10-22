"""Autopilot checks (needs the database).   python tests/test_autopilot.py
Uses a throwaway store and phone, restores any real job state, and removes what it created."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from jobs.autopilot import due, mark, run_cycle  # noqa: E402
from live.adapters.base import BaseAdapter  # noqa: E402
from live.pipeline import live_search, refresh_queries  # noqa: E402

STORE, KEY = "autotest_store", "zzauto galaxy"


class Shop(BaseAdapter):
    name = "test shop"

    def __init__(self, price):
        self.price, self.calls = price, 0

    def search(self, query):
        self.calls += 1
        return [{"store": STORE, "store_name": "Test Store", "sku": "A1", "origin": "test", "title": "Samsung Galaxy S24 5G (Onyx Black, 12GB RAM, 1024GB Storage)",
                 "price_inr": self.price, "url": "https://x/a1"}]


conn = psycopg.connect(os.environ["DATABASE_URL"])
usage = (conn.execute("SELECT calls FROM live_usage WHERE day = current_date").fetchone() or [0])[0]
saved = conn.execute("SELECT name, last_run, detail FROM job_state WHERE name LIKE 'autopilot:%'").fetchall()


def prices():
    return [float(r[0]) for r in conn.execute(
        "SELECT p.price_inr FROM price_history p JOIN listings l ON l.id = p.listing_id JOIN stores s ON s.id = l.store_id WHERE s.slug = %s ORDER BY p.observed_at", (STORE,))]


def cleanup():
    conn.rollback()
    ids = [r[0] for r in conn.execute("SELECT l.id FROM listings l JOIN stores s ON s.id = l.store_id WHERE s.slug = %s", (STORE,))]
    pids = {r[0] for r in conn.execute("SELECT DISTINCT product_id FROM listings WHERE id = ANY(%s) AND product_id IS NOT NULL", (ids,))}
    conn.execute("DELETE FROM price_history WHERE listing_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM listings WHERE id = ANY(%s)", (ids,))
    for pid in pids:
        if not conn.execute("SELECT 1 FROM listings WHERE product_id = %s LIMIT 1", (pid,)).fetchone():
            for t in ("forecasts", "price_moves"):
                conn.execute(f"DELETE FROM {t} WHERE product_id = %s", (pid,))
            conn.execute("DELETE FROM products WHERE id = %s", (pid,))
    conn.execute("DELETE FROM ingestion_runs WHERE store_id IS NULL OR store_id IN (SELECT id FROM stores WHERE slug = %s)", (STORE,))
    conn.execute("DELETE FROM stores WHERE slug = %s", (STORE,))
    conn.execute("DELETE FROM tracked_queries WHERE query_key LIKE 'zz%'")
    conn.execute("DELETE FROM live_cache WHERE query_key LIKE 'zz%'")
    conn.execute("DELETE FROM job_state WHERE name LIKE 'autopilot:%'")
    for name, last_run, detail in saved:
        conn.execute("INSERT INTO job_state (name, last_run, detail) VALUES (%s, %s, %s)", (name, last_run, detail))
    conn.execute("INSERT INTO live_usage (day, calls) VALUES (current_date, %s) ON CONFLICT (day) DO UPDATE SET calls = %s", (usage, usage))
    conn.commit()


try:
    cleanup()
    shop = Shop(99999)
    live_search(KEY, adapter=shop)
    shop.price = 94999

    # 1. the first cycle refreshes tracked prices; the weekly and daily jobs are due because they never ran
    assert due("autopilot:mine", 24 * 7) and due("autopilot:daily", 24)
    mark("autopilot:mine", "skipped in this test")                 # keep the test away from real brands
    r = run_cycle(adapter=shop, pause=0, subprocesses=False)
    assert r["refresh"]["refreshed"] >= 1 and prices() == [99999.0, 94999.0], (r, prices())
    assert "mine" not in r and r["daily"] == {}, "mining was marked as just done; the daily job ran with no steps"

    # 2. a second cycle straight after does not repeat the daily job, and refreshes nothing new
    calls = shop.calls
    r2 = run_cycle(adapter=shop, pause=0, subprocesses=False)
    assert "daily" not in r2 and "mine" not in r2 and shop.calls == calls, r2
    assert not due("autopilot:daily", 24) and due("autopilot:daily", 0) is not None

    # 3. the monthly allowance stops the refresh before it spends anything
    conn.execute("UPDATE tracked_queries SET last_refreshed = NULL WHERE query_key = %s", (KEY,))
    conn.commit()
    month = conn.execute("SELECT COALESCE(sum(calls), 0) FROM live_usage WHERE day >= date_trunc('month', current_date)").fetchone()[0]
    stop = refresh_queries(limit=5, stale_minutes=0, pause=0, monthly_cap=int(month), adapter=shop)
    assert stop["refreshed"] == 0 and "month" in (stop["stopped"] or ""), stop
    assert shop.calls == calls, "no call may be made once the monthly allowance is used up"
    print("PASS: the autopilot refreshes on every cycle, runs weekly and daily jobs once, and stops at the monthly allowance")
finally:
    cleanup()
