"""Catalog discovery checks (needs the database).   python tests/test_catalog.py
Uses a made-up brand ("Zztest"), and removes everything it created."""
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from catalog.miner import candidate, extract, known_models, record  # noqa: E402
from jobs.catalog import mine  # noqa: E402
from live.adapters.base import BaseAdapter  # noqa: E402
from matching.title_parser import load_models, parse_title  # noqa: E402

CSV = os.path.join(ROOT, "data", "models.csv")
conn = psycopg.connect(os.environ["DATABASE_URL"])
before = (conn.execute("SELECT calls FROM live_usage WHERE day = current_date").fetchone() or [0])[0]


def cleanup():
    conn.rollback()
    ids = [r[0] for r in conn.execute("SELECT l.id FROM listings l JOIN stores s ON s.id = l.store_id WHERE s.slug LIKE 'zztest_shop%'")]
    conn.execute("DELETE FROM price_history WHERE listing_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM listings WHERE id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM ingestion_runs WHERE store_id IS NULL OR store_id IN (SELECT id FROM stores WHERE slug LIKE 'zztest_shop%')")
    conn.execute("DELETE FROM stores WHERE slug LIKE 'zztest_shop%'")
    conn.execute("DELETE FROM tracked_queries WHERE query_key LIKE 'zztest%'")
    conn.execute("DELETE FROM live_cache WHERE query_key LIKE 'zztest%'")
    conn.execute("DELETE FROM catalog_models WHERE brand = 'Zztest'")
    conn.execute("DELETE FROM job_state WHERE name = 'mine:Zztest'")
    conn.execute("INSERT INTO live_usage (day, calls) VALUES (current_date, %s) ON CONFLICT (day) DO UPDATE SET calls = %s", (before, before))
    conn.commit()


def offers(model, stores):
    out = []
    for i, store in enumerate(stores):
        out.append({"title": f"Zztest {model} 5G (Blue, 8GB RAM, 256GB Storage) v{i}", "store": store})
    return out


try:
    cleanup()
    # 1. reading names: accessories never become phones
    assert candidate("Zztest Nova 9 5G (Blue, 8GB, 256GB)", ["Zztest"]) == ("Zztest", "Nova 9")
    assert candidate("Zztest Nova 9 back cover clear", ["Zztest"]) is None
    assert candidate("Unknownbrand X1 5G 8GB 256GB", ["Zztest"]) is None, "an unknown brand is not guessed"

    models = load_models(CSV, conn)
    known = known_models(models)

    # 2. enough evidence (3 listings, 2 stores) is approved automatically; less waits for a human
    found = extract(offers("Nova 9", ["amazon_in", "flipkart", "croma"]) + offers("Nova 8", ["amazon_in", "amazon_in"]), ["Zztest"])
    r = record(conn, found, known)
    st = dict(conn.execute("SELECT model, status FROM catalog_models WHERE brand = 'Zztest'").fetchall())
    assert st == {"Nova 9": "approved", "Nova 8": "proposed"}, st
    assert r == {"new": 2, "approved": 1}, r

    # 3. evidence adds up across runs
    record(conn, extract([{"title": "Zztest Nova 8 5G 8GB 256GB Other", "store": "croma"}], ["Zztest"]), known)
    assert conn.execute("SELECT status FROM catalog_models WHERE brand = 'Zztest' AND model = 'Nova 8'").fetchone()[0] == "approved"

    # 4. the matcher now knows the new brand and phone, though neither is in the CSV
    models = load_models(CSV, conn)
    assert "Zztest" in models
    p = parse_title("Zztest Nova 9 5G (Blue, 8GB RAM, 256GB Storage)", models)
    assert (p["brand"], p["model"], p["ram_gb"], p["storage_gb"], p["missing"]) == ("Zztest", "Nova 9", 8, 256, []), p
    assert "Zztest" not in load_models(CSV), "without the database it is still unknown"

    # 5. rejected stays rejected, however much evidence arrives
    out = subprocess.run([sys.executable, "jobs/catalog.py", "reject", "Zztest", "Nova 9"], cwd=ROOT, capture_output=True, text=True,
                         env=dict(os.environ))
    assert "rejected: Zztest Nova 9" in out.stdout, out.stdout + out.stderr
    record(conn, found, known)
    assert conn.execute("SELECT status FROM catalog_models WHERE brand = 'Zztest' AND model = 'Nova 9'").fetchone()[0] == "rejected"
    assert "Nova 9" not in [m for m, _ in load_models(CSV, conn).get("Zztest", [])], "a rejected model is not used"

    # 6. a human can approve a model nobody has seen, and the list shows it
    subprocess.run([sys.executable, "jobs/catalog.py", "approve", "Zztest", "Nova 7"], cwd=ROOT, capture_output=True, text=True, env=dict(os.environ))
    listing = subprocess.run([sys.executable, "jobs/catalog.py", "list"], cwd=ROOT, capture_output=True, text=True, env=dict(os.environ)).stdout
    assert "Nova 7" in listing and "approved" in listing and "rejected" in listing

    # 7. mining searches a brand and records what the results show (a stand-in source, no network)
    class Shop(BaseAdapter):
        name = "stub"
        def search(self, q):
            return offers("Nova 6", ["amazon_in", "flipkart", "croma"])
    res = mine(brands=["Zztest"], adapter=Shop(), query_for=lambda b: f"{b} phone")
    assert res["brands"] == ["Zztest"] and res["new"] == 1 and res["approved"] == 1, res
    assert conn.execute("SELECT 1 FROM job_state WHERE name = 'mine:Zztest'").fetchone(), "the run is remembered"
    # 8. seeding keeps the listings and prices AND learns the models (no matching run in this test)
    from jobs.catalog import seed
    class Shops(BaseAdapter):
        name = "stub"
        def search(self, q):
            return [{"store": s, "store_name": s, "sku": f"ZT{i}", "origin": "test", "title": f"Zztest Nova 5 5G (Blue, 8GB RAM, 256GB Storage) v{i}",
                     "price_inr": 30000 + i * 500, "url": "https://x/zt" + str(i)} for i, s in enumerate(["zztest_shop", "zztest_shop", "zztest_shop2"])]
    sres = seed(brands=["Zztest"], adapter=Shops(), link=False)
    assert sres["brands"] == ["Zztest"] and sres["offers"] == 3 and sres["approved"] == 1, sres
    assert conn.execute("SELECT count(*) FROM listings l JOIN stores s ON s.id = l.store_id WHERE s.slug LIKE 'zztest_shop%'").fetchone()[0] == 3, "listings are kept"
    assert conn.execute("SELECT status FROM catalog_models WHERE brand = 'Zztest' AND model = 'Nova 5'").fetchone()[0] == "approved"
    assert conn.execute("SELECT 1 FROM tracked_queries WHERE query_key = 'zztest smartphone'").fetchone(), "the search is remembered so it can be refreshed"
    print("PASS: new brands and phones are learned from evidence, kept out when wrong, rejections stick, and seeding keeps real listings")
finally:
    cleanup()
