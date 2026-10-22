"""Discover new phones from real listings.

Real shopping results name every phone currently on sale. This reads those titles, works out
the brand and model, and remembers what it saw. A model is approved automatically only when
it is backed by enough evidence (several different listings from several different stores);
everything else waits for a human, and a human can reject a wrong guess at any time.

This is a heuristic, not magic. A wrong model name would mis-group listings, which is why the
evidence rule exists and why `python jobs/catalog.py list` shows exactly what was approved.
"""
import hashlib
import json
import re

from live.filters import is_accessory
from matching.title_parser import BRAND_ALIASES

SPEC = re.compile(r"\b\d+\s*(?:gb|tb)\b", re.I)
CUT = re.compile(r"\s(?:5g|4g|3g|dual\s*sim|smartphone|mobile|unlocked|global|new|latest|with|by|for)\b|\(|\s-\s|\s\|\s|,|:", re.I)
COLORS = {"black", "white", "blue", "green", "red", "pink", "purple", "gold", "silver", "grey", "gray", "titanium",
          "midnight", "starlight", "cosmic", "orange", "yellow", "violet", "lavender", "mint", "cream", "bronze",
          "graphite", "obsidian", "onyx", "marble", "ocean", "phantom", "natural", "desert", "sky", "teal"}
PRODUCT_WORDS = {"galaxy": "Samsung", "iphone": "Apple", "pixel": "Google"}     # a phone line that implies its brand
GENERIC = {"galaxy", "iphone", "pixel", "phone", "note", "edge", "nord", "mobile"}
AUTO_MIN_TITLES, AUTO_MIN_MERCHANTS = 3, 2


def _brand_names(brands):
    names = {b.lower(): b for b in set(BRAND_ALIASES.values())}
    names.update({b.lower(): b for b in brands})
    return names


def candidate(title, brands=()):
    """('Samsung', 'Galaxy S26 Ultra') for 'Samsung Galaxy S26 Ultra 5G (Titanium, 12GB, 256GB)', or None."""
    t = re.sub(r"\((\d+[a-z]{0,2})\)", lambda m: "\u27e6" + m.group(1) + "\u27e7", title.strip())   # keep names like Phone (3a)
    cut = len(t)
    for rx in (SPEC, CUT):
        m = rx.search(t)
        if m:
            cut = min(cut, m.start())
    tokens = t[:cut].replace("\u27e6", "(").replace("\u27e7", ")").split()
    if not tokens:
        return None
    names = _brand_names(brands)
    first = re.sub(r"\W", "", tokens[0]).lower()
    if first in names:
        brand, rest = names[first], tokens[1:]
    elif first in PRODUCT_WORDS:
        brand, rest = PRODUCT_WORDS[first], tokens
    else:
        return None
    model = []
    for tok in rest:
        if tok.lower().strip("(),") in COLORS:
            break
        model.append(tok)
        if len(model) == 4:
            break
    if not model or (len(model) == 1 and model[0].lower() in GENERIC):
        return None
    name = " ".join(model)
    if is_accessory(name):
        return None
    if len(name) > 40 or not re.search(r"[A-Za-z0-9]", name):
        return None
    return brand, name


def extract(offers, brands=()):
    """offers: dicts with title and store. Returns {(brand, model): {'titles': set, 'merchants': set, 'example': str}}."""
    found = {}
    for o in offers:
        c = candidate(o.get("title", ""), brands)
        if not c:
            continue
        e = found.setdefault(c, {"titles": set(), "merchants": set(), "example": o["title"][:120]})
        e["titles"].add(hashlib.sha1(o["title"].lower().encode()).hexdigest()[:12])
        e["merchants"].add(o.get("store") or "?")
    return found


def record(conn, found, known, auto=True):
    """Save what was seen. `known` = {(brand, model)} already in the CSV or approved. Returns counts."""
    new = approved = 0
    for (brand, model), e in found.items():
        if (brand, model) in known:
            continue
        row = conn.execute("SELECT status, title_keys, merchants FROM catalog_models WHERE brand = %s AND model = %s",
                           (brand, model)).fetchone()
        titles = sorted(set(row[1] if row else []) | e["titles"])[:50]
        merchants = sorted(set(row[2] if row else []) | e["merchants"])[:20]
        status = row[0] if row else "proposed"
        by = None
        if status == "proposed" and auto and len(titles) >= AUTO_MIN_TITLES and len(merchants) >= AUTO_MIN_MERCHANTS:
            status, by = "approved", "auto"
            approved += 1
        if row is None:
            new += 1
        conn.execute(
            """INSERT INTO catalog_models (brand, model, status, title_keys, merchants, example, decided_by)
               VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
               ON CONFLICT (brand, model) DO UPDATE SET title_keys = EXCLUDED.title_keys, merchants = EXCLUDED.merchants,
                 status = EXCLUDED.status, last_seen = now(),
                 decided_by = COALESCE(EXCLUDED.decided_by, catalog_models.decided_by)""",
            (brand, model, status, json.dumps(titles), json.dumps(merchants), e["example"], by))
    conn.commit()
    return {"new": new, "approved": approved}


def known_models(models):
    return {(b, m) for b, ms in models.items() for m, _ in ms}
