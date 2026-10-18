"""Load prices from a CSV file (dataset source).

Example:
  python ingestion/run_csv.py data/sample_prices.csv --store amazon_in

Different column names:
  python ingestion/run_csv.py my.csv --store flipkart --sku-col id --title-col name --price-col sale_price

Price history (one row per listing per day):
  python ingestion/run_csv.py data/synthetic/prices_amazon_in.csv --store amazon_in --date-col date
"""
import argparse
import csv
import re
import sys
from datetime import datetime, timezone

from common import (connect, finish_run, get_store_id, load_observations,
                    now_utc, start_run)


def clean_price(value):
    """'₹1,29,999.00' -> 129999.0"""
    text = re.sub(r"[^0-9.]", "", str(value))
    return float(text) if text else None


def read_rows(path, a):
    rows, skipped = [], 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for rec in csv.DictReader(f):
            price = clean_price(rec.get(a.price_col, ""))
            sku, title = rec.get(a.sku_col), rec.get(a.title_col)
            if not (price and price > 0 and sku and title):
                skipped += 1
                continue
            row = {"store_sku": sku.strip(), "raw_title": title.strip(),
                   "price_inr": price, "url": rec.get(a.url_col) or None}
            if a.date_col and rec.get(a.date_col):
                row["observed_at"] = datetime.fromisoformat(rec[a.date_col]).replace(tzinfo=timezone.utc)
            rows.append(row)
    if a.date_col:   # history files must be loaded oldest first
        rows.sort(key=lambda r: r.get("observed_at") or datetime.min.replace(tzinfo=timezone.utc))
    return rows, skipped


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--store", required=True)
    p.add_argument("--sku-col", default="sku")
    p.add_argument("--title-col", default="title")
    p.add_argument("--price-col", default="price")
    p.add_argument("--url-col", default="url")
    p.add_argument("--date-col", default=None, help="column with YYYY-MM-DD, to load price history")
    a = p.parse_args()

    conn = connect()
    store_id = get_store_id(conn, a.store)
    run_id = start_run(conn, store_id)
    try:
        rows, skipped = read_rows(a.file, a)
        changed, unchanged = load_observations(conn, store_id, run_id, now_utc(), rows)
        conn.commit()
        finish_run(conn, run_id, "success", changed)
        print(f"Run {run_id}: read {len(rows)} rows | {changed} new or changed prices stored | "
              f"{unchanged} unchanged | {skipped} invalid rows skipped")
    except Exception as exc:
        conn.rollback()
        finish_run(conn, run_id, "failed", 0, str(exc))
        print(f"Run {run_id} FAILED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
