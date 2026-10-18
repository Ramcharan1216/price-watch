"""Forecast checks that need no database.   python tests/test_forecast.py"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from forecast.model import build_panel, evaluate, forecast_latest  # noqa: E402
from forecast.sale_calendar import days_to_next_sale, in_sale  # noqa: E402

assert in_sale(date(2026, 10, 3)) and not in_sale(date(2026, 10, 20))
assert days_to_next_sale(date(2026, 9, 28)) == 3

START = date(2024, 10, 17)


def make(n, base):
    days = [START + timedelta(days=d) for d in range(n)]
    return ([d.isoformat() for d in days],
            [base * (0.9 if in_sale(d) else 1.0) * (1 - 0.0002 * i) for i, d in enumerate(days)])


series = {pid: make(730, 40000 + 3000 * pid) for pid in range(1, 7)}
series[99] = make(60, 30000)                      # too little history
panel = build_panel(series)
assert 99 not in set(panel["product_id"]), "short history must be skipped"

rep = evaluate(panel, panel["date"].max())
assert set(rep["horizons"]) == {"7", "14", "30"}, rep["horizons"].keys()
for x in rep["horizons"].values():
    assert 0 <= x["coverage_model_pct"] <= 100 and x["mae_model_pct"] >= 0
    ev = x["event"]
    assert ev and ev["mae_model_pct"] <= ev["mae_naive_pct"], "model should beat 'no change' when a sale starts or ends"

rows = forecast_latest(panel)
assert len(rows) == 6 * 3, len(rows)
assert all(r["p10"] <= r["p50"] <= r["p90"] for r in rows), "quantiles must be ordered"
print("PASS: forecast handles calendar, skips short history, orders ranges, beats 'no change' around sales")
