"""API checks against your real database (needs data loaded and matched).
Run from the project folder:  python tests/test_api.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient  # noqa: E402
from api.main import app  # noqa: E402

c = TestClient(app)
assert c.get("/health").json() == {"status": "ok"}

res = c.get("/search", params={"q": "galaxy s24"}).json()["results"]
assert res, "search for 'galaxy s24' found nothing; load and match the data first"
assert all("galaxy" in r["name"].lower() and "s24" in r["name"].lower() for r in res)
assert c.get("/search", params={"q": "x"}).status_code == 422, "1-letter query should be rejected"

pid = res[0]["id"]
d = c.get(f"/products/{pid}").json()
prices = [o["price"] for o in d["offers"]]
assert d["offers"] and prices == sorted(prices), "offers should be sorted cheapest first"
assert d["cheapest"]["price"] == min(prices)
# links must never lead nowhere: demo URLs become a search on the store, real ones pass through
for o in d["offers"]:
    assert o["link_kind"] in ("listing", "search") and "example.com" not in o["url"], o
    if o["link_kind"] == "search" and o["store"] == "amazon_in":
        assert o["url"].startswith("https://www.amazon.in/s?k="), o["url"]
    if o["link_kind"] == "search" and o["store"] == "flipkart":
        assert o["url"].startswith("https://www.flipkart.com/search?q="), o["url"]

h = c.get(f"/products/{pid}/history", params={"days": 30}).json()
dates = [x["date"] for x in h["series"]]
assert dates == sorted(dates) and 0 < len(dates) <= 30
assert h["current_lowest"] == h["series"][-1]["lowest"]
assert h["stats"]["last_30_days"]["low"] <= h["stats"]["last_30_days"]["high"]
st = c.get("/status").json()
assert st["mode"] in ("demo", "mixed", "live") and st["demo_listings"] + st["live_listings"] > 0, st
assert c.get("/products/999999999").status_code == 404
assert c.get("/products/999999999/history").status_code == 404
print(f"PASS: API works. Example: {d['product']['name']} | cheapest {d['cheapest']['price']} "
      f"at {d['cheapest']['store']} | {h['days_of_history']} days of history")
