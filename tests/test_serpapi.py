"""SerpApi source checks, no network and no database.   python tests/test_serpapi.py
The canned answers follow the structure in SerpApi's Google Shopping documentation."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from live.adapters import get_adapter  # noqa: E402
from live.adapters.base import SourceError  # noqa: E402
from live.adapters.serpapi_shopping import SerpApiAdapter, parse, store_for  # noqa: E402
from live.filters import is_accessory, is_secondhand  # noqa: E402

LINK = "https://www.google.com/search?ibp=oshop&prds=catalogid:111"
DATA = {"shopping_results": [
    {"position": 1, "title": "Samsung Galaxy S26 5G (Onyx Black, 12GB, 256GB)", "source": "Amazon.in", "price": "₹79,999", "extracted_price": 79999, "product_id": "111", "product_link": LINK},
    {"position": 2, "title": "SAMSUNG Galaxy S26 5G (Onyx Black, 256 GB)  (12 GB RAM)", "source": "Flipkart", "price": "₹78,999.00", "extracted_price": 78999.0, "product_id": "111", "product_link": LINK},
    {"position": 3, "title": "Samsung Galaxy S26 5G 12GB 256GB", "source": "Croma", "price": "₹80,500", "extracted_price": 80500, "product_id": "111", "product_link": LINK},
    {"position": 4, "title": "Samsung Galaxy S26 5G 12GB 256GB", "source": "Croma", "price": "₹81,000", "extracted_price": 81000, "product_id": "111", "product_link": LINK},   # same store twice
    {"position": 5, "title": "Samsung Galaxy S26 Back Cover Clear", "source": "Case Store", "price": "₹499", "extracted_price": 499, "product_id": "222"},
    {"position": 6, "title": "Samsung Galaxy S26 Refurbished 128GB", "source": "ReCommerce", "price": "₹52,000", "extracted_price": 52000, "product_id": "333"},
    {"position": 7, "title": "Samsung Galaxy S26 (US model)", "source": "BestBuy", "price": "$799.00", "extracted_price": 799.0, "product_id": "444"},
    {"position": 8, "title": "Samsung Galaxy S26 5G", "source": "Reliance Digital", "price": "₹79,490", "extracted_price": 79490, "product_id": "111"},
    {"position": 9, "title": "Samsung Galaxy S26 5G", "source": "Some Seller", "price": "Price on request"},                  # no price
]}

offers = parse(DATA, "samsung galaxy s26")
by = {}
for o in offers:
    by.setdefault(o["store"], []).append(o)
assert set(by) == {"amazon_in", "flipkart", "croma", "reliance_digital"}, set(by)
assert len(by["croma"]) == 1 and by["croma"][0]["price_inr"] == 80500.0, "one listing per store and product, the cheapest"
assert by["amazon_in"][0]["store_name"] == "Amazon India" and by["flipkart"][0]["price_inr"] == 78999.0
assert all(o["origin"] == "serpapi" and o["confirmed"] and o["link_kind"] == "aggregator" and o["url"] == LINK for o in offers[:3])
assert {o["group"] for o in offers} == {"g111"}, "offers share Google's product id, so they group as one phone"
assert [o["sku"] for o in parse(DATA)] == [o["sku"] for o in offers], "the same listing keeps the same id between calls"

# filters
assert is_accessory("Samsung Galaxy S26 tempered glass") and not is_accessory("Realme Narzo 70 Pro Glass Green 8GB")
assert not is_accessory("phone case for galaxy", "phone case"), "a word the user searched for on purpose is allowed"
assert is_secondhand("iPhone 15 Renewed") and not is_secondhand("iPhone 15 new")
assert store_for("Amazon.in") == ("amazon_in", "Amazon India") and store_for("Vijay Sales")[0] == "vijay_sales"

# what is sent
sent = []
def get(params):
    sent.append(params)
    return DATA
os.environ.pop("SERPAPI_LOCATION", None)
r = SerpApiAdapter(get=get).search_full("galaxy s26")
p = sent[0]
assert (p["engine"], p["gl"], p["hl"], p["google_domain"], p["q"]) == ("google_shopping", "in", "en", "google.co.in", "galaxy s26"), p
assert "api_key" not in p and "location" not in p and len(r["offers"]) == 4
os.environ["SERPAPI_LOCATION"] = "Mumbai, Maharashtra, India"
sent.clear(); SerpApiAdapter(get=get).search_full("x"); assert sent[0]["location"] == "Mumbai, Maharashtra, India"
os.environ.pop("SERPAPI_LOCATION")

# problems are explained in plain words
for err, text in (("Invalid API key. Your API key should be here: https://serpapi.com/manage-api-key", "rejected"),
                  ("Your account has run out of searches.", "used up"),
                  ("Something unexpected happened", "SerpApi said")):
    try:
        parse({"error": err})
        raise AssertionError("should fail: " + err)
    except SourceError as e:
        assert text in str(e), str(e)
assert parse({"error": "Google hasn't returned any results for this query."}) == [], "no results is not an error"
assert parse({}) == []
os.environ.pop("SERPAPI_KEY", None)
try:
    SerpApiAdapter().search_full("galaxy s26")        # no key: must not touch the network
    raise AssertionError("should need a key")
except SourceError as e:
    assert "SERPAPI_KEY" in str(e)
from live.links import store_link  # noqa: E402
assert store_link("amazon_in", "x", LINK) == (LINK, "aggregator"), "a Google Shopping link is labelled as a seller list"
assert store_link("amazon_in", "x", "https://www.amazon.in/dp/B0X")[1] == "listing"
os.environ["LIVE_SOURCE"] = "serpapi"
assert get_adapter().name == "Google Shopping via SerpApi"
print("PASS: SerpApi source keeps real rupee listings, drops accessories and used items, groups by product, explains failures")
