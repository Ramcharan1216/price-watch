"""AI research adapter and link checks, no network and no database.   python tests/test_ai_web.py
The canned answers follow the structure in the Claude web-search documentation."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from live.adapters.ai_web import AiWebAdapter, extract, price_in_text  # noqa: E402
from live.adapters.base import SourceError  # noqa: E402
from live.links import store_link  # noqa: E402

AMZ = "https://www.amazon.in/Samsung-Galaxy-S24/dp/B0AAA"
FLP = "https://www.flipkart.com/samsung-galaxy-s24/p/itm123"
CRM = "https://www.croma.com/samsung-galaxy-s24/p/300001"


def answer(offers, summary="Found two stores.", cites=None, results=(AMZ, FLP, CRM), stop="end_turn"):
    """One API answer: a search, its results, then the JSON reply with citations."""
    return {"stop_reason": stop, "content": [
        {"type": "text", "text": "I'll search for that."},
        {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "galaxy s24 price india"}},
        {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1",
         "content": [{"type": "web_search_result", "url": u, "title": "Page " + u[-6:], "encrypted_content": "xx", "page_age": "1 day ago"} for u in results]},
        {"type": "text", "text": json.dumps({"summary": summary, "offers": offers}),
         "citations": [{"type": "web_search_result_location", "url": u, "title": "Page", "encrypted_index": "e", "cited_text": t}
                       for u, t in (cites or {}).items()]}]}


GOOD = [
    {"store": "Amazon", "title": "Samsung Galaxy S24 5G (8GB, 256GB)", "price_inr": 54999, "url": AMZ},
    {"store": "Flipkart", "title": "SAMSUNG Galaxy S24 5G (8 GB RAM, 256 GB)", "price_inr": 55999, "url": FLP},
    {"store": "Invented", "title": "Samsung Galaxy S24", "price_inr": 39999, "url": "https://www.fake-shop.in/s24"},   # no search returned this
    {"store": "Croma", "title": "Samsung Galaxy S24", "price_inr": "n/a", "url": CRM},                                  # unreadable price
    {"store": "Croma", "title": "Samsung Galaxy S24 cover", "price_inr": 5, "url": CRM},                               # implausible price
    {"store": "Croma", "title": "Samsung Galaxy S24 8GB 256GB", "price_inr": 56999, "url": "http://www.croma.com/x"},    # not https
]
CITES = {AMZ: "Samsung Galaxy S24 5G ... Price: ₹54,999.00 Free delivery"}      # only Amazon's price is quoted

# 1. links must come from a search; a price counts as confirmed only if the quote contains it
r = extract(answer(GOOD, cites=CITES)["content"])
by = {o["store_name"]: o for o in r["offers"]}
assert set(by) == {"Amazon India", "Flipkart"}, set(by)
assert by["Amazon India"]["confirmed"] is True and by["Flipkart"]["confirmed"] is False
assert by["Amazon India"]["store"] == "amazon_in" and by["Flipkart"]["store"] == "flipkart"
assert by["Amazon India"]["origin"] == "ai_web" and len(by["Amazon India"]["sku"]) == 16
assert r["summary"] == "Found two stores." and any(s["url"] == AMZ.replace("www.", "www.") or "amazon" in s["url"] for s in r["sources"])
again = extract(answer(GOOD, cites=CITES)["content"])["offers"][0]
assert again["sku"] == r["offers"][0]["sku"], "the same page must keep the same id"

assert price_in_text(54999, "Price: ₹54,999.00") and price_in_text(54999, "54999") and not price_in_text(54999, "₹154,999")

# 2. an unknown store gets a readable id from its domain
o = extract(answer([{"store": "X", "title": "Samsung Galaxy S24", "price_inr": 52000, "url": "https://www.reliancedigital.in/p/1"}],
                   results=("https://www.reliancedigital.in/p/1",))["content"])["offers"][0]
assert o["store"] == "reliancedigital_in" and o["store_name"] == "reliancedigital.in"

# 3. what the adapter sends
sent = []
def fake_post(payload):
    sent.append(payload)
    return answer(GOOD[:2], cites=CITES)
os.environ.pop("AI_ALLOWED_DOMAINS", None)
a = AiWebAdapter(post=fake_post)
full = a.search_full("galaxy s24")
p = sent[0]
assert p["tools"][0]["type"] == "web_search_20250305" and p["tools"][0]["name"] == "web_search" and p["tools"][0]["max_uses"] == 4
assert "allowed_domains" not in p["tools"][0] and p["messages"][0]["role"] == "user" and "galaxy s24" in p["messages"][0]["content"]
assert "never estimate or invent" in p["system"].lower() or "Never estimate or invent" in p["system"]
assert len(full["offers"]) == 2 and len(a.search("galaxy s24")) == 2
os.environ["AI_ALLOWED_DOMAINS"] = "amazon.in, flipkart.com"
sent.clear(); AiWebAdapter(post=fake_post).search_full("galaxy s24")
assert sent[0]["tools"][0]["allowed_domains"] == ["amazon.in", "flipkart.com"]
os.environ.pop("AI_ALLOWED_DOMAINS")

# 4. a paused search is continued with the earlier answer sent back unchanged
calls = []
def pausing(payload):
    calls.append(json.loads(json.dumps(payload)))
    if len(calls) == 1:
        return {"stop_reason": "pause_turn", "content": [{"type": "text", "text": "Still searching."},
                {"type": "web_search_tool_result", "tool_use_id": "s", "content": [{"type": "web_search_result", "url": AMZ, "title": "A", "encrypted_content": "keep-me"}]}]}
    return answer(GOOD[:1], cites=CITES, results=())
full = AiWebAdapter(post=pausing).search_full("galaxy s24")
assert len(calls) == 2 and calls[1]["messages"][-1]["role"] == "assistant"
assert calls[1]["messages"][-1]["content"][1]["content"][0]["encrypted_content"] == "keep-me", "must be sent back unchanged"
assert len(full["offers"]) == 1 and full["offers"][0]["confirmed"], "results from the paused turn still count"

# 5. failures are explained in plain words
for bad, text in ((lambda p: {"stop_reason": "end_turn", "content": [{"type": "text", "text": "I could not find anything."}]}, "could not be read"),
                  (lambda p: {"stop_reason": "end_turn", "content": [
                      {"type": "web_search_tool_result", "tool_use_id": "s", "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}},
                      {"type": "text", "text": '{"summary": "", "offers": []}'}]}, "max_uses_exceeded")):
    try:
        AiWebAdapter(post=bad).search_full("x")
        raise AssertionError("should fail")
    except SourceError as e:
        assert text in str(e), str(e)
os.environ.pop("ANTHROPIC_API_KEY", None)
try:
    AiWebAdapter().search_full("galaxy s24")      # no key: must not touch the network
    raise AssertionError("should need a key")
except SourceError as e:
    assert "ANTHROPIC_API_KEY" in str(e)
empty = extract(answer([], summary="Nothing found.", results=())["content"])
assert empty["offers"] == [] and empty["summary"] == "Nothing found."

# 6. links: real ones pass through, demo ones become a search on the store
assert store_link("amazon_in", "Samsung Galaxy S24", "https://www.amazon.in/dp/B0X") == ("https://www.amazon.in/dp/B0X", "listing")
l, k = store_link("amazon_in", "Samsung Galaxy S24 5G (Onyx Black)", "https://example.com/amazon_in/B0X")
assert k == "search" and l.startswith("https://www.amazon.in/s?k=Samsung+Galaxy+S24")
l, k = store_link("flipkart", "Samsung Galaxy S24", None)
assert k == "search" and l.startswith("https://www.flipkart.com/search?q=")
l, k = store_link("croma", "Samsung Galaxy S24", "https://example.com/croma/1")
assert k == "search" and l.startswith("https://www.google.com/search?q=") and "croma" in l
print("PASS: AI research keeps only real links, confirms prices against quotes, continues paused searches, explains failures; demo links open store searches")
