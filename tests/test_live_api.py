"""Endpoint behaviour for /live-search (no database, no real source).   python tests/test_live_api.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fastapi.testclient import TestClient  # noqa: E402
import api.main as m  # noqa: E402
from live.pipeline import LiveError, RateLimited  # noqa: E402

c = TestClient(m.app)
assert c.get("/live-search", params={"q": "ab"}).status_code == 422, "too short"

m.live_search = lambda q, **kw: {"query": q, "groups": [], "cached": False, "source": "stub"}
m._live_hits.clear()
assert c.get("/live-search", params={"q": "fairphone"}).json()["source"] == "stub"

def boom(exc):
    def f(q, **kw):
        raise exc
    return f

m._live_hits.clear(); m.live_search = boom(LiveError("The price source took too long to answer."))
r = c.get("/live-search", params={"q": "fairphone"}); assert r.status_code == 503 and "too long" in r.json()["detail"]
m._live_hits.clear(); m.live_search = boom(RateLimited("Today's live-search limit has been reached."))
r = c.get("/live-search", params={"q": "fairphone"}); assert r.status_code == 429 and "limit" in r.json()["detail"]

m._live_hits.clear(); m.live_search = lambda q, **kw: {"query": q, "groups": []}
codes = [c.get("/live-search", params={"q": "fairphone"}).status_code for _ in range(8)]
assert codes[:6] == [200] * 6 and codes[6:] == [429, 429], codes
print("PASS: /live-search rejects short queries, shows friendly errors, and limits each visitor to 6 a minute")
