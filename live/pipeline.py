"""Live search pipeline.

  question -> saved answer? -> daily quota check -> ask the source (with a time limit)
           -> read each title (brand, model, RAM, storage) -> save confirmed listings and prices
           -> start tracking -> answer with matched / unverified groups

Everything the source returns goes through the same matching code as the demo data, so a live
phone and a loaded phone end up as the same kind of row. Searches that found something are
remembered (tracked_queries) so a scheduled job can keep their prices fresh (refresh_queries).
"""
import concurrent.futures
import os
import re
import sys
import time
from datetime import datetime, timezone

import psycopg
from psycopg.types.json import Jsonb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from ingestion.common import load_observations  # noqa: E402
from live.adapters import get_adapter  # noqa: E402
from live.adapters.base import SourceError  # noqa: E402
from live.links import store_link  # noqa: E402
from matching.title_parser import AUTO_THRESHOLD, load_models, parse_title  # noqa: E402

MODELS_PATH = os.path.join(ROOT, "data", "models.csv")


class LiveError(Exception):
    """The source failed or was too slow. The message is safe to show to users."""


class RateLimited(LiveError):
    """Today's quota is used up."""


def normalize(q):
    return " ".join(re.findall(r"[a-z0-9+]+", q.lower()))


def _source():
    return os.environ.get("LIVE_SOURCE", "fake").lower()


def default_cap():
    """Daily limit on calls to the source. Paid sources start low."""
    return int(os.environ.get("LIVE_DAILY_CAP", {"ai_web": "30", "serpapi": "20"}.get(_source(), "200")))


def default_monthly_cap():
    """Monthly limit on calls (0 = none). SerpApi starts at 100 so a free plan cannot be overspent."""
    return int(os.environ.get("LIVE_MONTHLY_CAP", {"serpapi": "100"}.get(_source(), "0"))) or None


def default_timeout():
    return float(os.environ.get("LIVE_TIMEOUT", {"ai_web": "90", "serpapi": "30"}.get(_source(), "5")))


def _call(adapter, key, timeout):
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = ex.submit(adapter.search_full, key)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise LiveError("The price source took too long to answer. Please try again in a moment.")
    except SourceError as exc:
        raise LiveError(str(exc)) from exc
    except Exception as exc:
        raise LiveError("The price source could not be reached right now.") from exc
    finally:
        ex.shutdown(wait=False)


def _reserve_call(conn, cap, monthly_cap=None):
    row = conn.execute("SELECT calls FROM live_usage WHERE day = current_date").fetchone()
    if cap and row and row[0] >= cap:
        raise RateLimited("Today's live-search limit has been reached. Please try again tomorrow.")
    if monthly_cap:
        month = conn.execute("SELECT COALESCE(sum(calls), 0) FROM live_usage WHERE day >= date_trunc('month', current_date)").fetchone()[0]
        if month >= monthly_cap:
            raise RateLimited("This month's search allowance is used up. It resets at the start of next month.")
    conn.execute("INSERT INTO live_usage (day, calls) VALUES (current_date, 1) "
                 "ON CONFLICT (day) DO UPDATE SET calls = live_usage.calls + 1")
    conn.commit()


def _track(conn, key):
    conn.execute("INSERT INTO tracked_queries (query_key) VALUES (%s) ON CONFLICT (query_key) DO UPDATE "
                 "SET last_searched = now(), searches = tracked_queries.searches + 1", (key,))


def _process(conn, data, source, models):
    offers = data.get("offers") or []
    now = datetime.now(timezone.utc)
    run_id = conn.execute("INSERT INTO ingestion_runs (store_id) VALUES (NULL) RETURNING id").fetchone()[0]
    store_ids, groups, unconfirmed, skipped, changed = {}, {}, [], 0, 0

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
        link, kind = store_link(slug, title, o.get("url"))
        kind = o.get("link_kind") or kind                      # a source may say its link is an aggregator page
        offer = {"store": slug, "store_name": o.get("store_name") or slug, "title": title, "price": price,
                 "url": link, "link_kind": kind, "origin": o.get("origin")}
        if o.get("confirmed", True) is False:        # shown to the user, never saved as history
            unconfirmed.append(offer)
            continue
        sid = store_id(slug, offer["store_name"])
        c, _ = load_observations(conn, sid, run_id, now, [{"store_sku": sku, "raw_title": title, "price_inr": price,
                                                          "url": o.get("url"), "in_stock": o.get("in_stock"),
                                                          "source": o.get("origin")}])
        changed += c
        listing_id = conn.execute("SELECT id FROM listings WHERE store_id = %s AND store_sku = %s", (sid, sku)).fetchone()[0]
        p = parse_title(title, models)
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
                gk = ("u", (p["brand"] or title.split()[0]).lower(), p["ram_gb"], p["storage_gb"])
            else:
                gk = ("u", normalize(title))
            if o.get("group"):                                  # the source says these are the same product
                gk = ("u", o["group"])
            g = groups.setdefault(gk, {"product_id": None, "name": title, "verified": False, "offers": []})
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
    return {"source": source, "groups": out, "unconfirmed": sorted(unconfirmed, key=lambda x: x["price"]),
            "summary": data.get("summary", ""), "sources": data.get("sources", []),
            "skipped": skipped, "new_prices_stored": changed,
            "note": "Matched means we recognised the phone. Unverified means we could not confirm that "
                    "the listings are the same phone, so check the titles."}


def live_search(q, adapter=None, timeout=5.0, ttl=600, daily_cap=None, force=False, track=True, monthly_cap=None):
    key = normalize(q)
    if len(key) < 3:
        raise ValueError("Search phrase too short")
    adapter = adapter or get_adapter()
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        if not force:
            hit = conn.execute("SELECT result FROM live_cache WHERE query_key = %s "
                               "AND fetched_at > now() - make_interval(secs => %s)", (key, ttl)).fetchone()
            if hit:
                if track and hit[0].get("groups"):
                    _track(conn, key)
                    conn.commit()
                return {**hit[0], "query": key, "cached": True}
        _reserve_call(conn, daily_cap, monthly_cap)
        data = _call(adapter, key, timeout)
        result = _process(conn, data, adapter.name, load_models(MODELS_PATH, conn))
        conn.execute("INSERT INTO live_cache (query_key, source, result) VALUES (%s, %s, %s) "
                     "ON CONFLICT (query_key) DO UPDATE SET fetched_at = now(), source = EXCLUDED.source, "
                     "result = EXCLUDED.result", (key, adapter.name, Jsonb(result)))
        if track and result["groups"]:
            _track(conn, key)
        conn.commit()
        return {**result, "query": key, "cached": False}
    finally:
        conn.close()


def refresh_queries(limit=10, stale_minutes=60, max_age_days=30, pause=2.0, timeout=5.0, daily_cap=None, adapter=None, monthly_cap=None):
    """Re-ask the source for searches people made recently, so prices keep changing.
    Most-searched first. Stops cleanly when today's quota is used up."""
    adapter = adapter or get_adapter()
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        keys = [r[0] for r in conn.execute(
            """SELECT query_key FROM tracked_queries
               WHERE last_searched > now() - make_interval(days => %s)
                 AND (last_refreshed IS NULL OR last_refreshed < now() - make_interval(mins => %s))
               ORDER BY searches DESC, last_searched DESC LIMIT %s""", (max_age_days, stale_minutes, limit)).fetchall()]
    finally:
        conn.close()
    done = failed = changed = 0
    stopped = None
    for i, key in enumerate(keys):
        try:
            r = live_search(key, adapter=adapter, timeout=timeout, daily_cap=daily_cap, force=True, track=False, monthly_cap=monthly_cap)
            changed += r["new_prices_stored"]
            done += 1
            c2 = psycopg.connect(os.environ["DATABASE_URL"])
            try:
                c2.execute("UPDATE tracked_queries SET last_refreshed = now() WHERE query_key = %s", (key,))
                c2.commit()
            finally:
                c2.close()
        except RateLimited as exc:
            stopped = str(exc)
            break
        except LiveError:
            failed += 1
        if pause and i < len(keys) - 1:
            time.sleep(pause)
    return {"checked": len(keys), "refreshed": done, "failed": failed, "new_prices_stored": changed, "stopped": stopped}
