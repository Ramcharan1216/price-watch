"""Discover new phones from real listings, and manage what was found.

  python jobs/catalog.py seed               first-time setup with real data: search every brand once, keep the
                                            listings and prices, learn the models, then link everything
  python jobs/catalog.py mine --limit 3     search a few brands, learn new phone models from the results
  python jobs/catalog.py list               show discovered models (approved, proposed, rejected)
  python jobs/catalog.py approve "Samsung" "Galaxy S26"
  python jobs/catalog.py reject  "Samsung" "Galaxy S26 case"

A model is approved automatically only with enough evidence (several listings from several stores);
anything else waits here for you. Rejected models are never proposed again.
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
from catalog.miner import extract, known_models, record  # noqa: E402
from live.adapters import get_adapter  # noqa: E402
from live.pipeline import (MODELS_PATH, LiveError, RateLimited, _reserve_call, default_cap, default_monthly_cap,  # noqa: E402
                           default_timeout, live_search)
from matching.title_parser import BRAND_ALIASES, load_models  # noqa: E402


def brands_to_mine(conn, limit):
    """The brands we know, the ones mined longest ago first."""
    models = load_models(MODELS_PATH, conn)
    brands = sorted(set(models) | set(BRAND_ALIASES.values()))
    last = dict(conn.execute("SELECT replace(name, 'mine:', ''), last_run FROM job_state WHERE name LIKE 'mine:%'").fetchall())
    never = datetime(1970, 1, 1)
    return sorted(brands, key=lambda b: last.get(b, never).replace(tzinfo=None))[:limit]


def mine(limit=3, adapter=None, auto=True, query_for=lambda b: f"{b} smartphone", brands=None):
    """Search a few brands, record the phone models in the results. Returns what happened."""
    adapter = adapter or get_adapter()
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    out = {"brands": [], "new": 0, "approved": 0, "stopped": None}
    try:
        for brand in (brands or brands_to_mine(conn, limit)):
            try:
                _reserve_call(conn, default_cap(), default_monthly_cap())
            except RateLimited as exc:
                out["stopped"] = str(exc)
                break
            offers = adapter.search_full(query_for(brand))["offers"]
            models = load_models(MODELS_PATH, conn)
            r = record(conn, extract(offers, models.keys()), known_models(models), auto=auto)
            out["brands"].append(brand)
            out["new"] += r["new"]
            out["approved"] += r["approved"]
            conn.execute("INSERT INTO job_state (name, detail) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE "
                         "SET last_run = now(), detail = EXCLUDED.detail", (f"mine:{brand}", f"{len(offers)} offers"))
            conn.commit()
    finally:
        conn.close()
    return out


def seed(limit=20, adapter=None, auto=True, brands=None, link=True):
    """First-time setup with real data. Searches each brand once, KEEPS the listings and prices
    (unlike mine, which only reads names), learns the phone models, then links the listings."""
    adapter = adapter or get_adapter()
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    out = {"brands": [], "offers": 0, "new": 0, "approved": 0, "failed": 0, "stopped": None, "linked": None}
    try:
        for brand in (brands or brands_to_mine(conn, limit)):
            try:
                r = live_search(f"{brand} smartphone", adapter=adapter, timeout=default_timeout(),
                                daily_cap=default_cap(), monthly_cap=default_monthly_cap())
            except RateLimited as exc:
                out["stopped"] = str(exc)
                break
            except LiveError:
                out["failed"] += 1
                continue
            offers = [o for g in r["groups"] for o in g["offers"]] + r.get("unconfirmed", [])
            models = load_models(MODELS_PATH, conn)
            rec = record(conn, extract(offers, models.keys()), known_models(models), auto=auto)
            out["brands"].append(brand)
            out["offers"] += len(offers)
            out["new"] += rec["new"]
            out["approved"] += rec["approved"]
            conn.execute("INSERT INTO job_state (name, detail) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE "
                         "SET last_run = now(), detail = EXCLUDED.detail", (f"mine:{brand}", f"{len(offers)} offers"))
            conn.commit()
    finally:
        conn.close()
    if link and out["brands"]:       # listings stored before their model was learned get linked now
        r = subprocess.run([sys.executable, "matching/run_matching.py", "--redo"], cwd=ROOT, capture_output=True, text=True)
        out["linked"] = (r.stdout.strip().splitlines() or ["?"])[0] if r.returncode == 0 else "failed: " + (r.stderr.strip().splitlines() or ["?"])[-1]
    return out


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mine")
    m.add_argument("--limit", type=int, default=3)
    m.add_argument("--no-auto", action="store_true", help="never approve automatically")
    m.add_argument("--brand", action="append", help="mine only this brand (repeatable)")
    sd = sub.add_parser("seed")
    sd.add_argument("--limit", type=int, default=20, help="most brands to search")
    sd.add_argument("--brand", action="append", help="search only this brand (repeatable; also how a NEW brand is added)")
    sd.add_argument("--no-link", action="store_true")
    sub.add_parser("list")
    for name in ("approve", "reject"):
        c = sub.add_parser(name)
        c.add_argument("brand")
        c.add_argument("model")
    a = p.parse_args()
    if a.cmd == "seed":
        r = seed(a.limit, brands=a.brand, link=not a.no_link)
        print(f"Searched {len(r['brands'])} brands: {r['offers']} listings kept, {r['new']} new models seen, "
              f"{r['approved']} approved automatically, {r['failed']} searches failed"
              + (f" | stopped: {r['stopped']}" if r["stopped"] else "") + (f" | matching: {r['linked']}" if r["linked"] else ""))
        return
    if a.cmd == "mine":
        r = mine(a.limit, auto=not a.no_auto, brands=a.brand)
        print(f"Searched {len(r['brands'])} brands ({', '.join(r['brands'])}): {r['new']} new models seen, "
              f"{r['approved']} approved automatically" + (f" | stopped: {r['stopped']}" if r["stopped"] else ""))
        return
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        if a.cmd == "list":
            for st, br, mo, nt, nm, by in conn.execute(
                    "SELECT status, brand, model, jsonb_array_length(title_keys), jsonb_array_length(merchants), "
                    "COALESCE(decided_by, '') FROM catalog_models ORDER BY status, brand, model"):
                print(f"{st:<9} {br:<10} {mo:<28} {nt} listings, {nm} stores {('(' + by + ')') if by else ''}")
        else:
            status = "approved" if a.cmd == "approve" else "rejected"
            n = conn.execute("UPDATE catalog_models SET status = %s, decided_by = 'manual' WHERE brand = %s AND model = %s",
                             (status, a.brand, a.model)).rowcount
            if not n and status == "approved":     # approve a model nobody has seen yet
                conn.execute("INSERT INTO catalog_models (brand, model, status, decided_by) VALUES (%s, %s, 'approved', 'manual')", (a.brand, a.model))
                n = 1
            print(f"{status}: {a.brand} {a.model}" if n else "No such model. Run: python jobs/catalog.py list")


if __name__ == "__main__":
    main()
