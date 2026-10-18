"""Live search pipeline (Phase 8).

  question -> saved answer? -> daily quota check -> ask the source (with a time limit)
           -> read each title (brand, model, RAM, storage) -> save listings and prices
           -> start tracking -> answer with matched / unverified groups

Everything the source returns goes through the same matching code as the demo data,
so a live phone and a loaded phone end up as the same kind of row.
"""
import concurrent.futures
import os
import re
import sys
from datetime import datetime, timezone

import psycopg
from psycopg.types.json import Jsonb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from ingestion.common import load_observations  # noqa: E402
from live.adapters import get_adapter  # noqa: E402
from matching.title_parser import AUTO_THRESHOLD, load_models, parse_title  # noqa: E402

MODELS_PATH = os.path.join(ROOT, "data", "models.csv")


class LiveError(Exception):
    """The source failed or was too slow. The message is safe to show to users."""


class RateLimited(LiveError):
    """Today's quota is used up."""


def normalize(q):
    return " ".join(re.findall(r"[a-z0-9+]+", q.lower()))


def _call(adapter, key, timeout):
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = ex.submit(adapter.search, key)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise LiveError("The price source took too long to answer. Please try again in a moment.")
    except Exception as exc:
        raise LiveError("The price source could not be reached right now.") from exc
    finally:
        ex.shutdown(wait=False)


def _reserve_call(conn, cap):
    row = conn.execute("SELECT calls FROM live_usage WHERE day = current_date").fetchone()
    if cap and row and row[0] >= cap:
        raise RateLimited("Today's live-search limit has been reached. Please try again tomorrow.")
    conn.execute("INSERT INTO live_usage (day, calls) VALUES (current_date, 1) "
                 "ON CONFLICT (day) DO UPDATE SET calls = live_usage.calls + 1")
    conn.commit()


def _process(conn, offers, source, models):
    now = datetime.now(timezone.utc)
    run_id = conn.execute("INSERT INTO ingestion_runs (store_id) VALUES (NULL) RETURNING id").fetchone()[0]
    store_ids, groups, skipped, changed = {}, {}, 0, 0

    def store_id(slug, name):
        if slug not in store_ids:
            conn.execute("INSERT INTO stores (slug, name, data_source) VALUES (%s, %s, 'live') "
                         "ON CONFLICT (slug) DO NOTHING", (slug, name))
            store_ids[slug] = conn.execute("SELECT id FROM stores WHERE slug = %s", (slug,)).fetchone()[0]
        return store_ids[slug]

    for o in offers:
        try:
            price, title = float(o["price_inr"]), str(o["title"]).strip()
            slug, sku = str(o["store"]).strip(), str(o["sku"]).strip()
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if not (price > 0 and title and slug and sku):
            skipped += 1
            continue
        sid = store_id(slug, o.get("store_name") or slug)
        c, _ = load_observations(conn, sid, run_id, now, [{"store_sku": sku, "raw_title": title, "price_inr": price,
                                                          "url": o.get("url"), "in_stock": o.get("in_stock")}])
        changed += c
        listing_id = conn.execute("SELECT id FROM listings WHERE store_id = %s AND store_sku = %s", (sid, sku)).fetchone()[0]
        p = parse_title(title, models)
        offer = {"store": slug, "store_name": o.get("store_name") or slug, "title": title, "price": price, "url": o.get("url")}
        if not p["missing"] and p["confidence"] >= AUTO_THRESHOLD:
            name = f'{p["brand"]} {p["model"]} ({p["ram_gb"]}GB/{p["storage_gb"]}GB)'
            pid = conn.execute(
                """INSERT INTO products (brand, model, ram_gb, storage_gb, canonical_name) VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (brand, model, ram_gb, storage_gb) DO UPDATE SET brand = EXCLUDED.brand RETURNING id""",
                (p["brand"], p["model"], p["ram_gb"], p["storage_gb"], name)).fetchone()[0]
            conn.execute("UPDATE listings SET product_id = %s, match_confidence = %s, match_status = 'auto' WHERE id = %s",
                         (pid, p["confidence"], listing_id))
            g = groups.setdefault(("p", pid), {"product_id": pid, "name": name, "verified": True, "offers": []})
        else:
            # not sure what this is: keep the listing (unlinked) so a later matching run can retry
            conn.execute("UPDATE listings SET match_confidence = %s, match_status = 'unmatched' "
                         "WHERE id = %s AND product_id IS NULL", (p["confidence"], listing_id))
            if p["ram_gb"] and p["storage_gb"]:
                key = ("u", (p["brand"] or title.split()[0]).lower(), p["ram_gb"], p["storage_gb"])
            else:
                key = ("u", normalize(title))
            g = groups.setdefault(key, {"product_id": None, "name": title, "verified": False, "offers": []})
        g["offers"].append(offer)

    out = []
    for g in groups.values():
        g["offers"].sort(key=lambda x: x["price"])
        if not g["verified"]:
            g["name"] = g["offers"][0]["title"]
        g["cheapest"] = g["offers"][0]["price"]
        since = None
        if g["verified"]:
            since = conn.execute("SELECT min(h.observed_at)::date FROM price_history h JOIN listings l ON l.id = h.listing_id "
                                 "WHERE l.product_id = %s", (g["product_id"],)).fetchone()[0]
        g["tracking_since"] = (since or now.date()).isoformat()
        out.append(g)
    out.sort(key=lambda g: (not g["verified"], g["cheapest"]))
    conn.commit()
    return {"source": source, "groups": out, "skipped": skipped, "new_prices_stored": changed,
            "note": "Matched means we recognised the phone. Unverified means we could not confirm that "
                    "the listings are the same phone, so check the titles."}


def live_search(q, adapter=None, timeout=5.0, ttl=600, daily_cap=None):
    key = normalize(q)
    if len(key) < 3:
        raise ValueError("Search phrase too short")
    adapter = adapter or get_adapter()
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        hit = conn.execute("SELECT result FROM live_cache WHERE query_key = %s "
                           "AND fetched_at > now() - make_interval(secs => %s)", (key, ttl)).fetchone()
        if hit:
            return {**hit[0], "query": key, "cached": True}
        _reserve_call(conn, daily_cap)
        offers = _call(adapter, key, timeout)
        result = _process(conn, offers or [], adapter.name, load_models(MODELS_PATH))
        conn.execute("INSERT INTO live_cache (query_key, source, result) VALUES (%s, %s, %s) "
                     "ON CONFLICT (query_key) DO UPDATE SET fetched_at = now(), source = EXCLUDED.source, "
                     "result = EXCLUDED.result", (key, adapter.name, Jsonb(result)))
        conn.commit()
        return {**result, "query": key, "cached": False}
    finally:
        conn.close()
