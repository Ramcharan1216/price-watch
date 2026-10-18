"""Find big price moves and match each one with market signals that changed at the
same time (a sale window, memory chip prices, the dollar-rupee rate).

This is TIMING evidence, not proof of cause. Every reason is labelled strong, likely
or possible, carries its evidence, and a move with nothing behind it says so.
"""
from bisect import bisect_right
from datetime import date, timedelta

import numpy as np

from forecast.sale_calendar import SALES, sale_index

STEP_PCT, STEP_GAP = 0.01, 7             # a step is a 1% daily change; steps within 7 days are one move
SUDDEN_PCT = 0.04                        # a move counts if it adds up to 4% or more
GRADUAL_DAYS, GRADUAL_PCT = 60, 0.03     # a steady rise of 3% or more over two months
RECENT_DAYS = 365
ORDER = {"strong": 0, "likely": 1, "possible": 2}


def _d(x):
    return x if isinstance(x, date) else date.fromisoformat(x)


def _fmt(d):
    return f"{d.day} {d:%b}"


def _fmt_y(d):
    return f"{d.day} {d:%b %Y}"


def _groups(idx, gap, seg=None):
    """Group nearby indexes. With `seg`, indexes in different segments never merge."""
    out = []
    for i in idx:
        i = int(i)
        sg = seg[i] if seg is not None else None
        if out and i - out[-1][1] <= gap and out[-1][2] == sg:
            out[-1][1] = i
        else:
            out.append([i, i, sg])
    return [(a, b) for a, b, _ in out]


def sale_windows(d0, d1):
    return [(date(y, *s), date(y, *e)) for y in range(d0.year - 1, d1.year + 1) for s, e in SALES]


def detect_moves(dates, prices, recent_days=RECENT_DAYS):
    ds = [_d(x) for x in dates]
    p = np.asarray(prices, float)
    n = len(p)
    moves = []
    if n < 3:
        return moves
    d = np.zeros(n)
    d[1:] = p[1:] / p[:-1] - 1
    # a step inside a sale window is its own move: it must not absorb an unrelated nearby step
    seg = [((x.year, sale_index(x)) if sale_index(x) is not None else None) for x in ds]
    for sign in (-1, 1):             # falls and rises separately, so a sale drop and its rebound stay two moves
        for i0, i1 in _groups(np.where(sign * d >= STEP_PCT)[0], STEP_GAP, seg):
            base, end = p[i0 - 1], p[i1]            # measured from the price just BEFORE the first step
            ch = float(end / base - 1)
            if sign * ch >= SUDDEN_PCT:
                moves.append(dict(kind="sudden", i0=i0, i1=i1, start=ds[i0], end=ds[i1],
                                  start_price=float(base), end_price=float(end), change=ch))
    sudden_up = [m for m in moves if m["change"] > 0]
    if n > GRADUAL_DAYS + 1:
        r60 = np.full(n, np.nan)
        r60[GRADUAL_DAYS:] = p[GRADUAL_DAYS:] / p[:-GRADUAL_DAYS] - 1
        for i0, i1 in _groups(np.where(r60 >= GRADUAL_PCT)[0], 7):
            b = i0 - GRADUAL_DAYS
            if any(b <= m["i0"] <= i1 for m in sudden_up):   # just the echo of a sudden rise
                continue
            j = i0 + int(np.argmax(p[i0:i1 + 1] / p[b] - 1))
            moves.append(dict(kind="gradual", i0=i0, i1=i1, start=ds[b], end=ds[j],
                              start_price=float(p[b]), end_price=float(p[j]), change=float(p[j] / p[b] - 1)))
    cutoff = ds[-1] - timedelta(days=recent_days)
    return sorted([m for m in moves if m["end"] >= cutoff], key=lambda m: m["end"], reverse=True)


def _asof(sig, d):
    dates, vals = sig
    k = bisect_right(dates, d) - 1
    return vals[k] if k >= 0 else None


def _change(sig, d0, d1):
    a, b = _asof(sig, d0), _asof(sig, d1)
    return None if a is None or b is None or a == 0 else b / a - 1


def explain(move, ram_gb, signals):
    """signals: {kind: (sorted list of dates, list of values)}"""
    s, e, up = move["start"], move["end"], move["change"] > 0
    out = []
    for a, b in sale_windows(s, e):
        if not up and s <= b and e >= a:
            out.append(dict(type="sale", label="Sale period", confidence="strong",
                            evidence=f"The price fell during the {_fmt(a)} to {_fmt(b)} sale window."))
        if up and b < s <= b + timedelta(days=10):
            out.append(dict(type="sale_end", label="Sale ended", confidence="strong",
                            evidence=f"The price rose right after the {_fmt(a)} to {_fmt(b)} sale window ended."))
    soft = "likely" if move["kind"] == "gradual" else "possible"
    if ram_gb and ram_gb >= 8 and "dram_index" in signals:
        d0 = s - timedelta(days=60)
        ch = _change(signals["dram_index"], d0, e)
        if ch is not None and ((up and ch >= 0.10) or (not up and ch <= -0.10)):
            out.append(dict(type="memory", label="Memory chip costs " + ("rose" if up else "fell"), confidence=soft,
                            evidence=f"The memory (DRAM) price index moved {ch:+.0%} between {_fmt_y(d0)} and {_fmt_y(e)}."))
    if "usd_inr" in signals:
        d0 = s - timedelta(days=60)          # prices usually react a few weeks after the exchange rate
        ch = _change(signals["usd_inr"], d0, e)
        if ch is not None and ((up and ch >= 0.03) or (not up and ch <= -0.03)):
            out.append(dict(type="currency", label="Rupee " + ("weakened" if up else "strengthened"), confidence=soft,
                            evidence=f"The dollar-rupee rate moved {ch:+.1%} between {_fmt_y(d0)} and {_fmt_y(e)}."))
    out.sort(key=lambda r: ORDER[r["confidence"]])
    return out[:2]


def analyze_product(dates, prices, ram_gb, signals):
    res = []
    for m in detect_moves(dates, prices):
        res.append({"kind": m["kind"], "start": m["start"], "end": m["end"],
                    "change_pct": round(100 * m["change"], 2), "start_price": round(m["start_price"]),
                    "end_price": round(m["end_price"]), "reasons": explain(m, ram_gb, signals)})
    return res
