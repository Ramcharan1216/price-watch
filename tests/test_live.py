"""Live-search pipeline checks (needs the database).   python tests/test_live.py
Uses its own throwaway store and phones, and removes everything it created."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from live.adapters.base import BaseAdapter  # noqa: E402
from live.pipeline import LiveError, RateLimited, live_search  # noqa: E402

STORE = "livetest_store"


class Stub(BaseAdapter):
    name = "test source"

    def __init__(self, offers=None, delay=0, fail=False):
        self.offers, self.delay, self.fail, self.calls = offers or [], delay, fail, 0

    def search(self, query):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        return self.offers


def offer(sku, title, price, store=STORE):
    return {"store": store, "store_name": "Test Store", "sku": sku, "title": title, "price_inr": price, "url": "https://x/" + sku}


conn = psycopg.connect(os.environ["DATABASE_URL"])
conn.execute("DELETE FROM live_cache WHERE query_key LIKE 'zz%'")
conn.commit()
before = (conn.execute("SELECT calls FROM live_usage WHERE day = current_date").fetchone() or [0])[0]
made_products = set()


def cleanup():
    conn.rollback()
    ids = [r[0] for r in conn.execute("SELECT l.id FROM listings l JOIN stores s ON s.id = l.store_id WHERE s.slug = %s", (STORE,))]
    for r in conn.execute("SELECT DISTINCT product_id FROM listings WHERE id = ANY(%s) AND product_id IS NOT NULL", (ids,)).fetchall():
        made_products.add(r[0])
    conn.execute("DELETE FROM price_history WHERE listing_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM listings WHERE id = ANY(%s)", (ids,))
    for pid in made_products:     # only products nothing else points to
        if not conn.execute("SELECT 1 FROM listings WHERE product_id = %s LIMIT 1", (pid,)).fetchone():
            conn.execute("DELETE FROM forecasts WHERE product_id = %s", (pid,))
            conn.execute("DELETE FROM price_moves WHERE product_id = %s", (pid,))
            conn.execute("DELETE FROM products WHERE id = %s", (pid,))
    conn.execute("DELETE FROM ingestion_runs WHERE store_id IS NULL OR store_id IN (SELECT id FROM stores WHERE slug = %s)", (STORE,))
    conn.execute("DELETE FROM stores WHERE slug = %s", (STORE,))
    conn.execute("DELETE FROM live_cache WHERE query_key LIKE 'zz%'")
    conn.execute("INSERT INTO live_usage (day, calls) VALUES (current_date, %s) ON CONFLICT (day) DO UPDATE SET calls = %s",
                 (before, before))
    conn.commit()


try:
    # 1. a known model with a new variant becomes a MATCHED product and is tracked
    a = Stub([offer("T1", "Samsung Galaxy S24 5G (Onyx Black, 12GB RAM, 1024GB Storage)", 99999),
              offer("T2", "SAMSUNG Galaxy S24 5G (Marble Gray, 1024 GB)  (12 GB RAM)", 94999)])
    r = live_search("zzone galaxy", adapter=a)
    g = r["groups"][0]
    assert r["cached"] is False and len(r["groups"]) == 1 and g["verified"] and g["product_id"], r
    assert [o["price"] for o in g["offers"]] == [94999, 99999], "offers sorted cheapest first"
    n_hist = conn.execute("SELECT count(*) FROM price_history h JOIN listings l ON l.id = h.listing_id JOIN stores s ON s.id = l.store_id WHERE s.slug = %s", (STORE,)).fetchone()[0]
    assert n_hist == 2, "tracking starts: one price row per listing"

    # 2. asking again is answered from the saved copy: the source is not called
    r2 = live_search("ZZone  Galaxy", adapter=a)
    assert r2["cached"] is True and a.calls == 1, "second ask must come from the cache"

    # 3. same listings, same prices, no saved copy: no duplicate history
    conn.execute("DELETE FROM live_cache WHERE query_key LIKE 'zz%'")
    conn.commit()
    live_search("zzone galaxy", adapter=a)
    n2 = conn.execute("SELECT count(*) FROM price_history h JOIN listings l ON l.id = h.listing_id JOIN stores s ON s.id = l.store_id WHERE s.slug = %s", (STORE,)).fetchone()[0]
    assert a.calls == 2 and n2 == n_hist, "unchanged prices must not add history rows"

    # 4. an unknown phone is UNVERIFIED, grouped by RAM and storage, and left for review
    b = Stub([offer("U1", "Fairphone 5 5G (Black, 8GB RAM, 256GB Storage)", 60999),
              offer("U2", "FAIRPHONE 5 5G (Green, 256 GB)  (8 GB RAM)", 58999)])
    r = live_search("zztwo fairphone", adapter=b)
    assert len(r["groups"]) == 1 and not r["groups"][0]["verified"] and r["groups"][0]["product_id"] is None, r
    st = conn.execute("SELECT match_status, product_id FROM listings l JOIN stores s ON s.id = l.store_id WHERE s.slug = %s AND store_sku = 'U1'", (STORE,)).fetchone()
    assert st == ("unmatched", None), st

    # 5. bad rows are skipped, not fatal; nothing found is a clean empty answer
    c = Stub([offer("B1", "Samsung Galaxy S24 5G (Onyx Black, 12GB RAM, 1024GB Storage)", 0), {"store": STORE}])
    r = live_search("zzthree bad", adapter=c)
    assert r["skipped"] == 2 and r["groups"] == [], r
    assert live_search("zzfour none", adapter=Stub([]))["groups"] == []

    # 6. a slow source and a broken source give friendly errors, and nothing is saved as an answer
    for bad, label in ((Stub(delay=1.5), "slow"), (Stub(fail=True), "broken")):
        try:
            live_search("zzfive " + label, adapter=bad, timeout=0.3)
            raise AssertionError(label + " source should fail")
        except LiveError as e:
            assert "price source" in str(e)
    assert conn.execute("SELECT 1 FROM live_cache WHERE query_key LIKE 'zzfive%'").fetchone() is None

    # 7. the daily quota stops calls to the source
    conn.execute("INSERT INTO live_usage (day, calls) VALUES (current_date, 5) ON CONFLICT (day) DO UPDATE SET calls = 5")
    conn.commit()
    quota = Stub([offer("Q1", "Samsung Galaxy S24 5G (Onyx Black, 12GB RAM, 1024GB Storage)", 99999)])
    try:
        live_search("zzsix quota", adapter=quota, daily_cap=5)
        raise AssertionError("quota should stop this")
    except RateLimited:
        assert quota.calls == 0, "the source must not be called once the quota is used"
    try:
        live_search("zz", adapter=quota)
        raise AssertionError("too short")
    except ValueError:
        pass
    print("PASS: live search matches, caches, tracks without duplicates, flags unknown phones, and fails politely")
finally:
    cleanup()
