"""AI research source: Claude searches the web and reports what it found, with sources.

Setup (see docs/ai-research.md):
  1. ANTHROPIC_API_KEY=...   in .env (never in the code)
  2. An administrator must enable web search in the Claude Console
  3. LIVE_SOURCE=ai_web      in .env, then restart the server

What keeps it honest:
  * every link must be one that a search actually returned (invented links are dropped)
  * a price is CONFIRMED only if it appears in the text Claude quoted from that same page
  * unconfirmed offers are shown with a warning and are never saved as price history
  * sources are returned so the page can show them (the API terms ask for citations)

Cost: web search is billed per search plus normal tokens, so LIVE_DAILY_CAP matters.
"""
import hashlib
import json
import os
import re
from urllib.parse import urlparse

import httpx

from .base import BaseAdapter, SourceError

API_URL = "https://api.anthropic.com/v1/messages"
STORES = {"amazon.in": ("amazon_in", "Amazon India"), "flipkart.com": ("flipkart", "Flipkart"),
          "croma.com": ("croma", "Croma")}

SYSTEM = (
    "You research prices of phones and electronic appliances for an Indian price-comparison website. "
    "Use web search to find current listings for the product the user names, on Indian online stores. "
    "Rules: report only what you actually saw in search results. Never estimate or invent a price, a store "
    "or a link. Every offer needs the exact page URL where you saw it, and its price in Indian rupees as a "
    "whole number. Skip results that show no price. Quote the price text from the page when you cite it. "
    "If you find nothing, return an empty list. "
    'Reply with one JSON object and nothing else: {"summary": "<two plain sentences on what you found>", '
    '"offers": [{"store": "<store name>", "title": "<listing title as shown>", "price_inr": <number>, '
    '"url": "<exact page URL>"}]}'
)


def _host(url):
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _norm_url(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc.lower()}{p.path.rstrip('/')}"      # query and fragment ignored


def _store_for(url):
    host = _host(url)
    for domain, (slug, name) in STORES.items():
        if host == domain or host.endswith("." + domain):
            return slug, name
    return re.sub(r"[^a-z0-9]+", "_", host).strip("_"), host


def price_in_text(price, text):
    """True if `price` appears as a number in `text` (17,999 / 17999 / 17,999.00 all match 17999)."""
    needle = str(int(price))
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text or ""):
        if re.sub(r"\D", "", m.group(0).split(".")[0]) == needle:
            return True
    return False


def _json_from(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise SourceError("The research finished, but the answer could not be read. Please try again.")
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        raise SourceError("The research finished, but the answer could not be read. Please try again.")


def read_blocks(all_blocks, final_blocks):
    """Collect what the search returned (links) and what was quoted (citations)."""
    retrieved, cites, sources, errors = {}, {}, {}, []
    for b in all_blocks:
        kind = b.get("type")
        if kind == "web_search_tool_result":
            content = b.get("content")
            if isinstance(content, dict):                     # an error object, e.g. max_uses_exceeded
                errors.append(content.get("error_code", "error"))
                continue
            for r in content or []:
                if r.get("url"):
                    retrieved[_norm_url(r["url"])] = r.get("title") or r["url"]
        elif kind == "text":
            for c in b.get("citations") or []:
                if c.get("url"):
                    k = _norm_url(c["url"])
                    cites.setdefault(k, []).append(c.get("cited_text") or "")
                    sources[k] = c.get("title") or c["url"]
    text = "".join(b.get("text", "") for b in final_blocks if b.get("type") == "text")
    return text, retrieved, cites, sources, errors


def extract(all_blocks, final_blocks=None):
    """Turn a Messages API answer into offers + summary + sources."""
    text, retrieved, cites, sources, errors = read_blocks(all_blocks, final_blocks if final_blocks is not None else all_blocks)
    data = _json_from(text)
    offers = []
    for o in data.get("offers") or []:
        url, title = str(o.get("url", "")).strip(), str(o.get("title", "")).strip()
        try:
            price = int(round(float(str(o.get("price_inr")).replace(",", ""))))
        except (TypeError, ValueError):
            continue
        key = _norm_url(url)
        if not (url.startswith("https://") and title and 100 <= price <= 1_000_000):
            continue
        if key not in retrieved and key not in cites:          # a link no search returned: drop it
            continue
        slug, name = _store_for(url)
        offers.append({"store": slug, "store_name": name, "sku": hashlib.sha1(key.encode()).hexdigest()[:16].upper(),
                       "title": title[:200], "price_inr": price, "url": url, "in_stock": None, "origin": "ai_web",
                       "confirmed": any(price_in_text(price, t) for t in cites.get(key, []))})
    shown = {**retrieved, **sources}
    return {"offers": offers, "summary": str(data.get("summary", ""))[:400],
            "sources": [{"url": u, "title": t} for u, t in list(shown.items())[:8]], "errors": errors}


class AiWebAdapter(BaseAdapter):
    name = "AI web research (with sources)"

    def __init__(self, post=None):
        self.key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        self.max_searches = int(os.environ.get("AI_MAX_SEARCHES", "4"))
        self.domains = [d.strip() for d in os.environ.get("AI_ALLOWED_DOMAINS", "").split(",") if d.strip()]
        self._post = post or self._http_post

    def _http_post(self, payload):
        if not self.key:
            raise SourceError("The AI research source is not set up yet. Add ANTHROPIC_API_KEY to the .env file.")
        r = httpx.post(API_URL, json=payload, timeout=120,
                       headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        if r.status_code == 401:
            raise SourceError("The AI research key was rejected. Check ANTHROPIC_API_KEY in the .env file.")
        if r.status_code == 400 and "web search" in r.text.lower():
            raise SourceError("Web search is not enabled for this Anthropic account. An administrator can turn it on in the Claude Console.")
        if r.status_code == 429:
            raise SourceError("The AI research service is busy. Please try again in a minute.")
        r.raise_for_status()
        return r.json()

    def search_full(self, query):
        tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": self.max_searches}
        if self.domains:
            tool["allowed_domains"] = self.domains
        messages = [{"role": "user", "content": f"Find current prices in India for: {query}"}]
        all_blocks, final = [], []
        for _ in range(4):                                     # a long search can pause; continue up to 3 times
            resp = self._post({"model": self.model, "max_tokens": 2000, "system": SYSTEM, "tools": [tool], "messages": messages})
            final = resp.get("content", [])
            all_blocks += final
            if resp.get("stop_reason") != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": final}]     # sent back unchanged, as the docs require
        if os.environ.get("AI_DEBUG"):
            os.makedirs(os.path.join("data", "raw"), exist_ok=True)
            with open(os.path.join("data", "raw", "ai_last_response.json"), "w", encoding="utf-8") as f:
                json.dump(all_blocks, f, indent=1)
        result = extract(all_blocks, final)
        if not result["offers"] and result["errors"]:
            raise SourceError("The web search could not run (" + ", ".join(sorted(set(result["errors"]))) + "). Please try again later.")
        return result

    def search(self, query):
        return self.search_full(query)["offers"]
