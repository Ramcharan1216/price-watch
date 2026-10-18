"""The contract every price source follows.

An adapter turns a search phrase into a list of OFFERS. Each offer is a dict:
    store       short id of the store, e.g. "amazon_in"
    store_name  display name, e.g. "Amazon India"
    sku         the store's own id for the listing (must stay the same between calls)
    title       the listing title, exactly as the store shows it
    price_inr   the price in rupees, as a number
    url         link to the listing (optional)
    in_stock    True or False (optional)

The rest of the pipeline never knows which source is behind it, so replacing the
source means writing one new file like this and nothing else.
"""


class BaseAdapter:
    name = "unnamed source"      # shown to users: "Live prices from <name>"

    def search(self, query):
        raise NotImplementedError
