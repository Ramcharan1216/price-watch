"""Price Intel API (Phase 3).

Run from the project folder:
  uvicorn api.main:app --reload
Then open http://127.0.0.1:8000/docs
"""
import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

from .series import daily_series, product_series, window_stats
from live.links import store_link
from live.pipeline import LiveError, RateLimited, default_cap, default_timeout, live_search

load_dotenv()
app = FastAPI(title="Price Intel API", version="0.3")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["GET"], allow_headers=["*"])


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def num(x):
    return None if x is None else float(x)


def iso(x):
    return None if x is None else x.isoformat()


LATEST = ("JOIN LATERAL (SELECT price_inr, observed_at, source FROM price_history h "
          "WHERE h.listing_id = l.id ORDER BY observed_at DESC LIMIT 1) cur ON true")


@app.get("/health")
def health():
    with db() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


SELECT_SQL = ("SELECT p.id, p.canonical_name AS name, p.brand, p.model, p.ram_gb, p.storage_gb, "
              "count(DISTINCT l.store_id) AS store_count, min(cur.price_inr) AS lowest_price "
              "FROM products p JOIN listings l ON l.product_id = p.id " + LATEST)
ORDERS = {"name": "p.canonical_name", "price_asc": "min(cur.price_inr), p.canonical_name",
          "price_desc": "min(cur.price_inr) DESC, p.canonical_name"}


@app.get("/search")
def search(q: str = Query("", max_length=80), brand: str | None = Query(None, max_length=40),
           max_price: int | None = Query(None, ge=1),
           sort: str = Query("name", pattern="^(name|price_asc|price_desc)$"),
           limit: int = Query(30, ge=1, le=50)):
    q = q.strip()
    if q and len(q) < 2:
        raise HTTPException(422, "Type at least 2 letters")
    like = [f"%{t.replace(chr(92), '').replace('%', '').replace('_', '')}%" for t in q.split()]

    def run(conn, where, wparams, order, oparams):
        conds, params = [where], list(wparams)
        if brand:
            conds.append("p.brand = %s")
            params.append(brand)
        having = ""
        if max_price:
            having = "HAVING min(cur.price_inr) <= %s"
            params.append(max_price)
        sql = (SELECT_SQL + " WHERE " + " AND ".join(conds) + " GROUP BY p.id " + having
               + " ORDER BY " + order + " LIMIT %s")
        return conn.execute(sql, [*params, *oparams, limit]).fetchall()

    with db() as conn:
        rows = run(conn, " AND ".join(["p.canonical_name ILIKE %s"] * len(like)) if like else "TRUE",
                   like, ORDERS[sort], [])
        if not rows and q:       # typo tolerance via trigram similarity, if the extension is available
            try:
                rows = run(conn, "similarity(p.canonical_name, %s) > 0.25", [q],
                           "max(similarity(p.canonical_name, %s)) DESC", [q])
            except psycopg.Error:
                conn.rollback()
                rows = []
    for r in rows:
        r["lowest_price"] = num(r["lowest_price"])
    return {"query": q, "results": rows}


@app.get("/brands")
def brands():
    with db() as conn:
        rows = conn.execute("SELECT p.brand, count(*) AS n FROM products p WHERE EXISTS "
                            "(SELECT 1 FROM listings l WHERE l.product_id = p.id) "
                            "GROUP BY p.brand ORDER BY p.brand").fetchall()
    return {"brands": rows}


_cache = {}


def cached(key, ttl, build):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = build()
    _cache[key] = (time.time(), value)
    return value


@app.get("/deals")
def deals(limit: int = Query(6, ge=1, le=20)):
    """Phones whose cheapest price today is well under their recent average."""
    def build():
        out = []
        with db() as conn:
            names = {r["slug"]: r["name"] for r in conn.execute("SELECT slug, name FROM stores").fetchall()}
            for p in conn.execute("SELECT id, canonical_name AS name FROM products ORDER BY id").fetchall():
                s = product_series(conn, p["id"])
                if len(s) < 30:
                    continue
                recent = [x["lowest"] for x in s[-90:]]
                cur, avg = recent[-1], sum(recent) / len(recent)
                below = (cur / avg - 1) * 100
                if below <= -3:
                    by = s[-1]["by_store"]
                    best = min(by, key=by.get)
                    out.append({"id": p["id"], "name": p["name"], "current": cur, "average_90d": round(avg),
                                "below_pct": round(below, 1), "store": names.get(best, best)})
        return sorted(out, key=lambda x: x["below_pct"])
    items = cached("deals", 600, build)
    return {"deals": items[:limit],
            "note": "Phones whose cheapest price today is at least 3% under their 90-day average."}


@app.get("/products/{product_id}")
def product(product_id: int):
    with db() as conn:
        p = conn.execute("SELECT id, canonical_name AS name, brand, model, ram_gb, storage_gb "
                         "FROM products WHERE id = %s", (product_id,)).fetchone()
        if not p:
            raise HTTPException(404, "Product not found")
        offers = conn.execute(
            f"""SELECT s.slug AS store, s.name AS store_name, l.raw_title AS title, l.url,
                       cur.price_inr AS price, cur.source AS source, l.last_checked
                FROM listings l JOIN stores s ON s.id = l.store_id {LATEST}
                WHERE l.product_id = %s ORDER BY cur.price_inr, s.slug""", (product_id,)).fetchall()
    for o in offers:
        o["price"], o["last_checked"] = num(o["price"]), iso(o["last_checked"])
        o["url"], o["link_kind"] = store_link(o["store"], o["title"], o["url"])   # demo links become store searches
    return {"product": p, "offers": offers, "cheapest": offers[0] if offers else None}


@app.get("/products/{product_id}/history")
def history(product_id: int, days: int = Query(90, ge=7, le=730)):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM products WHERE id = %s", (product_id,)).fetchone():
            raise HTTPException(404, "Product not found")
        rows = conn.execute(
            """SELECT h.listing_id, s.slug, h.observed_at::date AS d, h.price_inr
               FROM price_history h JOIN listings l ON l.id = h.listing_id
               JOIN stores s ON s.id = l.store_id
               WHERE l.product_id = %s ORDER BY h.listing_id, h.observed_at""", (product_id,)).fetchall()
        last = conn.execute("SELECT max(last_checked)::date AS d FROM listings WHERE product_id = %s",
                            (product_id,)).fetchone()["d"]
    end_day = max([last or date.min, *[r["d"] for r in rows]] or [date.today()])
    full = daily_series(rows, end_day)
    series = full[-days:]
    stats = {f"last_{n}_days": window_stats(full, n) for n in (30, 90, 365)}
    current = full[-1]["lowest"] if full else None
    avg30 = (stats["last_30_days"] or {}).get("average")
    return {"product_id": product_id, "days_of_history": len(full), "current_lowest": current,
            "vs_30_day_average_pct": round((current / avg30 - 1) * 100, 1) if current and avg30 else None,
            "stats": stats, "series": series,
            "note": "Stats cover only the days we have recorded."}


@app.get("/products/{product_id}/forecast")
def forecast(product_id: int):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM products WHERE id = %s", (product_id,)).fetchone():
            raise HTTPException(404, "Product not found")
        rows = conn.execute(
            """SELECT * FROM forecasts WHERE product_id = %s AND made_on =
               (SELECT max(made_on) FROM forecasts WHERE product_id = %s) ORDER BY horizon_days""",
            (product_id, product_id)).fetchall()
        rep = conn.execute("SELECT report FROM model_reports ORDER BY id DESC LIMIT 1").fetchone()
    if not rows:
        return {"available": False, "reason": "Not enough price history yet. We need about four months "
                                             "of recorded prices before we forecast."}
    tested = (rep["report"]["horizons"] if rep else {})
    return {"available": True, "made_on": iso(rows[0]["made_on"]), "current": num(rows[0]["current_price"]),
            "model_version": rows[0]["model_version"],
            "horizons": [{"days": r["horizon_days"], "low": num(r["p10"]), "expected": num(r["p50"]),
                          "high": num(r["p90"]), "naive_low": num(r["naive_p10"]), "naive_high": num(r["naive_p90"]),
                          "range_held_pct": (tested.get(str(r["horizon_days"])) or {}).get("coverage_model_pct")}
                         for r in rows]}


@app.get("/accuracy")
def accuracy():
    with db() as conn:
        rep = conn.execute("SELECT report, created_at FROM model_reports ORDER BY id DESC LIMIT 1").fetchone()
    if not rep:
        return {"available": False}
    return {"available": True, "report": rep["report"], "created_at": iso(rep["created_at"])}


@app.get("/products/{product_id}/moves")
def moves(product_id: int, limit: int = Query(6, ge=1, le=20)):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM products WHERE id = %s", (product_id,)).fetchone():
            raise HTTPException(404, "Product not found")
        rows = conn.execute(
            """SELECT start_date, end_date, kind, change_pct, start_price, end_price, reasons
               FROM price_moves WHERE product_id = %s ORDER BY end_date DESC LIMIT %s""",
            (product_id, limit)).fetchall()
    return {"product_id": product_id,
            "moves": [{"start": iso(r["start_date"]), "end": iso(r["end_date"]), "kind": r["kind"],
                       "direction": "up" if r["change_pct"] > 0 else "down", "change_pct": num(r["change_pct"]),
                       "start_price": num(r["start_price"]), "end_price": num(r["end_price"]),
                       "reasons": r["reasons"]} for r in rows],
            "note": "Reasons are matched by timing: we look for sales, memory chip prices and exchange "
                    "rates that moved at the same time. That points to a likely cause; it does not prove one."}


_live_hits = {}


def _live_rate_ok(ip, limit=6, window=60):
    """At most `limit` live searches per minute per visitor."""
    now = time.time()
    hits = [t for t in _live_hits.get(ip, []) if now - t < window]
    ok = len(hits) < limit
    if ok:
        hits.append(now)
    _live_hits[ip] = hits
    return ok


@app.get("/live-search")
def live(request: Request, q: str = Query(..., min_length=3, max_length=60)):
    """Ask the price source for phones that are not in our database yet."""
    ip = request.client.host if request.client else "unknown"
    if not _live_rate_ok(ip):
        raise HTTPException(429, "You are searching too fast. Please wait a minute and try again.")
    try:
        return live_search(q, daily_cap=default_cap(), timeout=default_timeout())
    except RateLimited as e:
        raise HTTPException(429, str(e))
    except LiveError as e:
        raise HTTPException(503, str(e))


# ---- Website (Phase 4): http://127.0.0.1:8000/ opens the app ----
WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "web")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/app/")


if os.path.isdir(WEB_DIR):
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
