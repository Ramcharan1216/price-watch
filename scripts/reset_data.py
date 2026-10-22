"""Delete ALL loaded prices, listings, products, forecasts and saved live searches (stores and the learned catalog are kept).
Use this before loading a new dataset.   python scripts/reset_data.py --yes"""
import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()
if "--yes" not in sys.argv:
    sys.exit("This deletes all prices, listings, products, forecasts and saved live searches. Run again with --yes to confirm.")
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute("TRUNCATE price_history, raw_responses, ingestion_runs, listings, products "
                 "RESTART IDENTITY CASCADE")
    conn.execute("TRUNCATE model_reports RESTART IDENTITY")
    conn.execute("TRUNCATE live_cache, tracked_queries")
print("Data cleared. Stores kept.")
