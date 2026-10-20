"""Links that always work.

Real listing URLs pass through untouched. The simulated demo data uses placeholder
URLs (https://example.com/...), so for those we open a SEARCH on the store instead,
and say so, rather than showing a link that goes nowhere."""
from urllib.parse import quote_plus

PLACEHOLDER = ("https://example.com",)


def store_link(store, title, url):
    """Returns (link, kind) where kind is 'listing' (a real page) or 'search' (a search on the store)."""
    if url and not url.startswith(PLACEHOLDER):
        return url, "listing"
    q = quote_plus((title or "")[:80])
    if store == "amazon_in":
        return f"https://www.amazon.in/s?k={q}", "search"
    if store == "flipkart":
        return f"https://www.flipkart.com/search?q={q}", "search"
    return f"https://www.google.com/search?q={q}+{quote_plus((store or '').replace('_', ' '))}", "search"
