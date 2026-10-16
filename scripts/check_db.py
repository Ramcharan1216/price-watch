"""Phase 0 check: confirms the database is up and the schema exists."""
import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()
EXPECTED = {"stores", "products", "listings", "ingestion_runs",
            "raw_responses", "price_history", "signals"}

try:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'").fetchall()
        found = {r[0] for r in rows}
        missing = EXPECTED - found
        stores = conn.execute("SELECT slug FROM stores ORDER BY id").fetchall()
except Exception as exc:
    print(f"FAIL: could not check database: {exc}")
    sys.exit(1)

if missing:
    print(f"FAIL: missing tables: {sorted(missing)}")
    sys.exit(1)
print("OK: schema is in place")
print("Stores:", ", ".join(s[0] for s in stores))
