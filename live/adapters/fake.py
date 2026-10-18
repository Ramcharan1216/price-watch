"""A pretend price source for building and testing without any key.

It knows a small catalog of phones that are NOT in the demo database, answers the
same question the same way every time, and sometimes leaves a store out, like a real
source would. Set FAKE_DELAY=8 (seconds) to test timeouts, FAKE_FAIL=1 to test outages.
"""
import hashlib
import os
import re
import time
from datetime import date

from .base import BaseAdapter

STORES = [("amazon_in", "Amazon India"), ("flipkart", "Flipkart"), ("croma", "Croma")]

# brand, model, base price (INR, simulated), [(ram, storage)], colors
CATALOG = [
    ("Nothing", "Phone (2)", 44999, [(12, 256)], ["Dark Grey", "White"]),
    ("Google", "Pixel 9", 74999, [(12, 256)], ["Obsidian", "Porcelain"]),
    ("OnePlus", "Nord 4", 29999, [(8, 128), (12, 256)], ["Mercurial Silver", "Obsidian Midnight"]),
    ("Motorola", "Edge 50 Pro", 31999, [(12, 256)], ["Luxe Lavender", "Moonlight Pearl"]),
    ("Fairphone", "5", 59999, [(8, 256)], ["Black", "Green"]),
    ("Samsung", "Galaxy S24", 74999, [(8, 512)], ["Onyx Black", "Marble Gray"]),
    ("Samsung", "Galaxy Z Flip6", 109999, [(12, 256)], ["Blue", "Silver Shadow"]),
    ("Apple", "iPhone 16", 79900, [(8, 128), (8, 256)], ["Black", "Ultramarine"]),
    ("Realme", "GT 6", 40999, [(12, 256)], ["Razor Green", "Fluid Silver"]),
]


def _u(*parts):
    """A repeatable pseudo-random number between 0 and 1 from the given parts."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _norm(text):
    return " ".join(re.findall(r"[a-z0-9+]+", text.lower()))


def _title(store, brand, model, ram, sto, color):
    if store == "amazon_in":
        return f"{brand} {model} 5G ({color}, {ram}GB RAM, {sto}GB Storage)"
    if store == "flipkart":
        return f"{brand.upper()} {model} 5G ({color}, {sto} GB)  ({ram} GB RAM)"
    return f"{brand} {model} {ram}GB {sto}GB {color}"


def _sku(store, *parts):
    h = hashlib.sha256("|".join((store,) + tuple(map(str, parts))).encode()).hexdigest()
    if store == "amazon_in":
        return "B0" + h[:8].upper()
    if store == "flipkart":
        return "MOB" + h[:13].upper()
    return str(int(h[:6], 16) % 900000 + 100000)


class FakeAdapter(BaseAdapter):
    name = "the demo source (simulated)"

    def search(self, query):
        if float(os.environ.get("FAKE_DELAY", "0") or 0):
            time.sleep(float(os.environ["FAKE_DELAY"]))
        if os.environ.get("FAKE_FAIL"):
            raise RuntimeError("simulated outage")
        tokens = _norm(query).split()
        week = date.today().isocalendar()[1]
        offers = []
        for brand, model, base, variants, colors in CATALOG:
            for i, (ram, sto) in enumerate(variants):
                for color in colors:
                    if not tokens or not all(t in _norm(f"{brand} {model} {ram}gb {sto}gb {color}") for t in tokens):
                        continue
                    for store, store_name in STORES:
                        if _u("down", store, brand, model, week) < 0.12:     # this store has no listing today
                            continue
                        price = (base * (1 + 0.12 * i) * (0.97 + 0.06 * _u("off", store, brand, model, ram, sto))
                                 * (1 + 0.04 * (_u("week", week, store, brand, model) - 0.5)))
                        sku = _sku(store, brand, model, ram, sto, color)
                        offers.append({"store": store, "store_name": store_name, "sku": sku,
                                       "title": _title(store, brand, model, ram, sto, color),
                                       "price_inr": int(round(price / 1000.0)) * 1000 - 1,
                                       "url": f"https://example.com/{store}/{sku}", "in_stock": True})
        return offers[:24]
