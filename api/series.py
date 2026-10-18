"""Daily price series per product (shared by the API and the forecast job)."""
from datetime import date, timedelta

from psycopg.rows import dict_row


def daily_series(rows, end_day):
    """rows: price-change rows ordered by listing then time -> one lowest price per day."""
    per_listing = {}
    for r in rows:
        per_listing.setdefault(r["listing_id"], []).append((r["d"], float(r["price_inr"]), r["slug"]))
    if not per_listing:
        return []
    start = min(v[0][0] for v in per_listing.values())
    days = [start + timedelta(days=i) for i in range((end_day - start).days + 1)]
    state = {}
    idx = {k: 0 for k in per_listing}
    series = []
    for day in days:
        for lid, changes in per_listing.items():
            while idx[lid] < len(changes) and changes[idx[lid]][0] <= day:
                state[lid] = (changes[idx[lid]][1], changes[idx[lid]][2])
                idx[lid] += 1
        if not state:
            continue
        by_store = {}
        for price, slug in state.values():
            by_store[slug] = min(price, by_store.get(slug, price))
        series.append({"date": day.isoformat(), "lowest": min(by_store.values()), "by_store": by_store})
    return series


def window_stats(series, n):
    part = [x["lowest"] for x in series[-n:]]
    if not part:
        return None
    return {"days": len(part), "low": min(part), "high": max(part),
            "average": round(sum(part) / len(part), 2)}


def product_series(conn, product_id):
    cur = conn.cursor(row_factory=dict_row)
    rows = cur.execute(
        """SELECT h.listing_id, s.slug, h.observed_at::date AS d, h.price_inr
           FROM price_history h JOIN listings l ON l.id = h.listing_id
           JOIN stores s ON s.id = l.store_id
           WHERE l.product_id = %s ORDER BY h.listing_id, h.observed_at""", (product_id,)).fetchall()
    last = cur.execute("SELECT max(last_checked)::date AS d FROM listings WHERE product_id = %s",
                       (product_id,)).fetchone()["d"]
    end_day = max([last or date.min, *[r["d"] for r in rows]])
    return daily_series(rows, end_day)
