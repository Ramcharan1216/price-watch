"""Detect price moves and their likely reasons for every product.
   python reasons/run_reasons.py"""
import os
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ingestion"))
from psycopg.types.json import Jsonb  # noqa: E402
from common import connect  # noqa: E402
from api.series import product_series  # noqa: E402
from reasons.engine import analyze_product  # noqa: E402

conn = connect()
signals = {}
for kind, d, v in conn.execute("SELECT kind, observed_on, value FROM signals ORDER BY kind, observed_on").fetchall():
    ds, vs = signals.setdefault(kind, ([], []))
    ds.append(d)
    vs.append(float(v))
if not signals:
    print("No market signals loaded. Without them only sale-window reasons can be found "
          "(run: python scripts/load_signals.py).")

products = conn.execute("SELECT id, ram_gb FROM products ORDER BY id").fetchall()
conn.execute("DELETE FROM price_moves")
total, kinds, reasons, unexplained = 0, Counter(), Counter(), 0
for pid, ram in products:
    s = product_series(conn, pid)
    if len(s) < 30:
        continue
    for m in analyze_product([x["date"] for x in s], [x["lowest"] for x in s], ram, signals):
        conn.execute(
            """INSERT INTO price_moves (product_id, start_date, end_date, kind, change_pct, start_price, end_price, reasons)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (product_id, start_date, kind) DO NOTHING""",
            (pid, m["start"], m["end"], m["kind"], m["change_pct"], m["start_price"], m["end_price"], Jsonb(m["reasons"])))
        total += 1
        kinds[m["kind"]] += 1
        if m["reasons"]:
            reasons[m["reasons"][0]["type"]] += 1
        else:
            unexplained += 1
conn.commit()
print(f"{total} price moves in the last year across {len(products)} products ({dict(kinds)})")
if total:
    print(f"With a reason: {total - unexplained} ({100 * (total - unexplained) / total:.0f}%) | "
          f"no clear reason: {unexplained} ({100 * unexplained / total:.0f}%)")
    print("Top reason by type:", dict(reasons))
