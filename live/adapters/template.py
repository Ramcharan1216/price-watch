"""YOUR TURN: a starting point for a real price source.

Steps (do them once you have access to a source):
 1. Read the source's documentation: how do you search, what is the key called?
 2. Put the key in your .env file (never in the code), e.g.  MY_SOURCE_KEY=...
 3. In search(): call the source with the query, then turn each result into an offer
    dict (see base.py). Skip results with no price. Keep `sku` stable between calls.
 4. Set LIVE_SOURCE=template in .env, restart the server, and try a search.
Nothing else in the project changes.
"""
from .base import BaseAdapter


class TemplateAdapter(BaseAdapter):
    name = "your real source"

    def search(self, query):
        raise NotImplementedError("Write the real lookup here. See the steps at the top of this file.")
