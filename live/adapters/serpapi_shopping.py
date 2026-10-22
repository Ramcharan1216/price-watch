"""Real prices: Google Shopping through SerpApi (https://serpapi.com/google-shopping-api).

Setup (docs/real-data.md):
  1. Create a SerpApi account (it has a free plan) and copy your key.
  2. Put it in .env:   SERPAPI_KEY=your-key        (never in the code)
  3. LIVE_SOURCE=serpapi   in .env, then restart.

What it returns: one offer per store listing that Google Shopping shows for the search, with the
store name, the price in rupees, and a link to Google's page listing the sellers. Accessories and
used or refurbished items are dropped. Prices in other currencies are dropped.

Each search is billed against your SerpApi plan, so LIVE_MONTHLY_CAP matters (default 100).
"""
import hashlib
import json
import os
import re

import httpx

from live.filters import is_accessory, is_secondhand
from .base import BaseAdapter, SourceError

API_URL = "https://serpapi.com/search"
RUPEE = re.compile(r"₹|\brs\.?\b|\binr\b", re.I)


def store_for(merchant):
    m = re.sub(r"[^a-z0-9]+", " ", merchant.lower()).strip()
    if "amazon" in m:
        return "amazon_in", "Amazon India"
    if "flipkart" in m:
        return "flipkart", "Flipkart"
    if "croma" in m:
        return "croma", "Croma"
    return re.sub(r"[^a-z0-9]+", "_", m).strip("_")[:30] or "unknown", merchant.strip()


def parse(data, query=""):
    """SerpApi google_shopping answer -> offers."""
    if data.get("error"):
        err = str(data["error"])
        if "hasn't returned any results" in err.lower() or "no results" in err.lower():
            return []
        low = err.lower()
        if "invalid api key" in low or "api key" in low and "invalid" in low:
            raise SourceError("The SerpApi key was rejected. Check SERPAPI_KEY in the .env file.")
        if "run out" in low or "exhausted" in low or "searches" in low and "month" in low:
            raise SourceError("This month's SerpApi searches are used up. They reset at the start of your billing month.")
        raise SourceError("SerpApi said: " + err[:160])
    best = {}
    for r in data.get("shopping_results") or []:
        title, merchant = (r.get("title") or "").strip(), (r.get("source") or "").strip()
        price = r.get("extracted_price")
        if not title or not merchant or price is None or not RUPEE.search(str(r.get("price", ""))):
            continue                                    # no price, no store, or not in rupees
        if is_accessory(title, query) or is_secondhand(title, query):
            continue
        slug, name = store_for(merchant)
        pid = str(r.get("product_id") or "")
        sku = hashlib.sha1(f"{pid or title.lower()}|{slug}".encode()).hexdigest()[:16].upper()
        offer = {"store": slug, "store_name": name, "sku": sku, "title": title[:200], "price_inr": float(price),
                 "url": r.get("product_link") or r.get("link"), "link_kind": "aggregator", "in_stock": None,
                 "origin": "serpapi", "confirmed": True, "group": ("g" + pid) if pid else None}
        if sku not in best or offer["price_inr"] < best[sku]["price_inr"]:      # one listing per store and product
            best[sku] = offer
    return list(best.values())


class SerpApiAdapter(BaseAdapter):
    name = "Google Shopping via SerpApi"

    def __init__(self, get=None):
        self.key = os.environ.get("SERPAPI_KEY", "").strip()
        self.location = os.environ.get("SERPAPI_LOCATION", "").strip()
        self._get = get or self._http_get

    def _http_get(self, params):
        if not self.key:
            raise SourceError("The price source is not set up yet. Add SERPAPI_KEY to the .env file.")
        r = httpx.get(API_URL, params={**params, "api_key": self.key}, timeout=30)
        if r.status_code in (401, 403):
            raise SourceError("The SerpApi key was rejected. Check SERPAPI_KEY in the .env file.")
        if r.status_code == 429:
            raise SourceError("SerpApi is limiting requests right now. Please try again in a minute.")
        if r.status_code >= 400 and "application/json" not in r.headers.get("content-type", ""):
            r.raise_for_status()
        return r.json()

    def search_full(self, query):
        params = {"engine": "google_shopping", "q": query, "gl": "in", "hl": "en", "google_domain": "google.co.in"}
        if self.location:
            params["location"] = self.location
        data = self._get(params)
        if os.environ.get("SERPAPI_DEBUG"):         # keep the raw answer so a mismatch with the docs can be diagnosed
            os.makedirs(os.path.join("data", "raw"), exist_ok=True)
            with open(os.path.join("data", "raw", "serpapi_last_response.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
        offers = parse(data, query)
        return {"offers": offers, "summary": "", "sources": []}

    def search(self, query):
        return self.search_full(query)["offers"]
