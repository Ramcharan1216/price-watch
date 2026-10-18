"""Known sale windows (announced in advance, so safe to use as model inputs).
Simulated calendar: Republic Day sale, mid-year sale, festive sale.
With real data, replace these with the real announced dates."""
from datetime import date

SALES = [((1, 15), (1, 20)), ((6, 20), (6, 25)), ((10, 1), (10, 8))]


def _windows(year):
    return [(date(year, *s), date(year, *e)) for s, e in SALES]


def sale_index(d):
    for k, (a, b) in enumerate(_windows(d.year)):
        if a <= d <= b:
            return k
    return None


def in_sale(d):
    return sale_index(d) is not None


def days_to_next_sale(d, cap=120):
    best = cap
    for y in (d.year, d.year + 1):
        for a, _ in _windows(y):
            if a >= d:
                best = min(best, (a - d).days)
    return best


def days_since_sale_end(d, cap=120):
    best = cap
    for y in (d.year - 1, d.year):
        for _, b in _windows(y):
            if b < d:
                best = min(best, (d - b).days)
    return best
