"""Reason engine checks, no database.   python tests/test_reasons.py"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from reasons.engine import analyze_product  # noqa: E402

START = date(2025, 11, 1)
N = 400
days = [START + timedelta(days=i) for i in range(N)]
dates = [d.isoformat() for d in days]


def sig(fn):
    return (days, [fn(d) for d in days])


flat = lambda d: 100.0                                              # noqa: E731
dram_up = lambda d: 100 * (1 + 0.25 * min(1, max(0, (d - date(2026, 3, 1)).days / 100)))  # noqa: E731

# 1. a flat price has no moves
assert analyze_product(dates, [50000] * N, 8, {}) == []

# 2. a drop inside the October sale window, then a rebound just after it
prices = [50000 * (0.90 if date(2026, 10, 1) <= d <= date(2026, 10, 8) else 1.0) for d in days]
m = {x["start"].isoformat(): x for x in analyze_product(dates, prices, 8, {})}
drop, rise = m["2026-10-01"], m["2026-10-09"]
assert drop["change_pct"] < -9 and drop["reasons"][0]["type"] == "sale" and drop["reasons"][0]["confidence"] == "strong"
assert rise["change_pct"] > 9 and rise["reasons"][0]["type"] == "sale_end"

# 3. a slow 6% rise while memory prices rise: memory is the reason (only for 8GB+ phones)
slow = [50000 * (1 + 0.06 * min(1, max(0, (d - date(2026, 4, 1)).days / 75))) for d in days]
sigs = {"dram_index": sig(dram_up), "usd_inr": sig(flat)}
up = [x for x in analyze_product(dates, slow, 12, sigs) if x["change_pct"] > 0]
assert up and up[0]["kind"] == "gradual" and up[0]["reasons"][0]["type"] == "memory", up
assert "rose" in up[0]["reasons"][0]["label"] and "DRAM" in up[0]["reasons"][0]["evidence"]
small = [x for x in analyze_product(dates, slow, 4, sigs) if x["change_pct"] > 0]
assert small and small[0]["reasons"] == [], "4GB phones should not be blamed on memory chips"

# 4. the same rise with flat memory prices: honest "no reason"
none = [x for x in analyze_product(dates, slow, 12, {"dram_index": sig(flat), "usd_inr": sig(flat)}) if x["change_pct"] > 0]
assert none and none[0]["reasons"] == []

# 5. a 5% rupee move can explain a rise; a 1% move cannot
usd_up = lambda d: 83 * (1 + 0.05 * min(1, max(0, (d - date(2026, 3, 1)).days / 60)))  # noqa: E731
step = [50000 * (1.05 if d >= date(2026, 5, 1) else 1.0) for d in days]
r = [x for x in analyze_product(dates, step, 4, {"usd_inr": sig(usd_up)}) if x["change_pct"] > 0][0]
assert r["reasons"] and r["reasons"][0]["type"] == "currency"
usd_small = lambda d: 83 * (1 + 0.01 * min(1, max(0, (d - date(2026, 3, 1)).days / 60)))  # noqa: E731
r2 = [x for x in analyze_product(dates, step, 4, {"usd_inr": sig(usd_small)}) if x["change_pct"] > 0][0]
assert r2["reasons"] == [], "a 1% rupee move is too small to blame"
# 6. a small step just BEFORE a sale window must not be merged into the sale move
pre = [50000.0] * N
for i, d in enumerate(days):
    if d >= date(2026, 6, 18): pre[i] = 48250.0                                    # -3.5% on 18 Jun
    if date(2026, 6, 20) <= d <= date(2026, 6, 25): pre[i] = 48250.0 * 0.94        # sale
mv = {m["start"].isoformat(): m for m in analyze_product(dates, pre, 8, {})}
assert "2026-06-20" in mv and "2026-06-18" not in mv, sorted(mv)
assert -6.5 < mv["2026-06-20"]["change_pct"] < -5.5 and mv["2026-06-20"]["reasons"][0]["type"] == "sale"
print("PASS: reasons engine finds moves, attributes sales/memory/rupee, and admits when there is no reason")
