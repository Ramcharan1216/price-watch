"""The contract every price source follows.

An adapter turns a search phrase into OFFERS. Each offer is a dict:
    store       short id of the store, e.g. "amazon_in"
    store_name  display name, e.g. "Amazon India"
    sku         the store's own id for the listing (must stay the same between calls)
    title       the listing title, as the store shows it
    price_inr   the price in rupees, as a number
    url         link to the listing (optional)
    in_stock    True or False (optional)
    confirmed   False if the price could not be checked against its source (optional; default True).
                Unconfirmed offers are shown to the user but never saved as price history.
    origin      short tag for where the price came from, e.g. "ai_web" (optional)

search_full() may also return a short `summary` and a list of `sources` (title + url) so the
page can show what the research found and where.
"""


class SourceError(Exception):
    """A source problem whose message is safe and useful to show to the user."""


class BaseAdapter:
    name = "unnamed source"      # shown to users: "Live prices from <name>"

    def search(self, query):
        raise NotImplementedError

    def search_full(self, query):
        return {"offers": self.search(query), "summary": "", "sources": []}
