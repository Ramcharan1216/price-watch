"""Train, evaluate and store forecasts.   python forecast/run_forecast.py"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ingestion"))
from psycopg.types.json import Jsonb  # noqa: E402
from common import connect  # noqa: E402
from api.series import product_series  # noqa: E402
from forecast.model import VERSION, build_panel, evaluate, forecast_latest  # noqa: E402

conn = connect()
pids = [r[0] for r in conn.execute(
    "SELECT DISTINCT l.product_id FROM listings l JOIN price_history h ON h.listing_id = l.id "
    "WHERE l.product_id IS NOT NULL").fetchall()]
series = {}
for pid in pids:
    s = product_series(conn, pid)
    if s:
        series[pid] = ([x["date"] for x in s], [x["lowest"] for x in s])

asof = None
if "--as-of" in sys.argv:        # python forecast/run_forecast.py --as-of 2026-10-17
    asof = sys.argv[sys.argv.index("--as-of") + 1]
    series = {pid: ([d for d in ds if d <= asof], ps[:sum(1 for d in ds if d <= asof)]) for pid, (ds, ps) in series.items()}
    print(f"Using data up to {asof} only")
panel = build_panel(series)
if panel.empty:
    sys.exit(f"No product has enough history yet ({len(series)} products checked). Load longer history first.")
print(f"{len(series)} products, {panel['product_id'].nunique()} with enough history, {len(panel)} training rows")

report = evaluate(panel, panel["date"].max())
rows = forecast_latest(panel)
for r in rows:
    conn.execute(
        """INSERT INTO forecasts (product_id, made_on, horizon_days, current_price, p10, p50, p90,
                                  naive_p10, naive_p90, model_version)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (product_id, made_on, horizon_days) DO UPDATE SET
             current_price=EXCLUDED.current_price, p10=EXCLUDED.p10, p50=EXCLUDED.p50, p90=EXCLUDED.p90,
             naive_p10=EXCLUDED.naive_p10, naive_p90=EXCLUDED.naive_p90, model_version=EXCLUDED.model_version""",
        (r["product_id"], r["made_on"], r["horizon_days"], r["current"], r["p10"], r["p50"], r["p90"],
         r["naive_p10"], r["naive_p90"], VERSION))
conn.execute("INSERT INTO model_reports (report) VALUES (%s)", (Jsonb(report),))
conn.commit()

print(f"Stored {len(rows)} forecasts. Test period: last {report['test_days']} days (model trained only on data before {report['cutoff']}).")
print(f"{'horizon':>8} {'our miss':>9} {'no-change miss':>15} {'range held':>11} {'(aim 80)':>9}")
for h, x in report["horizons"].items():
    print(f"{h + ' days':>8} {x['mae_model_pct']:>8}% {x['mae_naive_pct']:>14}% {x['coverage_model_pct']:>10}%")
