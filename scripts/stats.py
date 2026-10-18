"""Quick look at what is in the database."""
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    for t in ("stores", "listings", "price_history", "ingestion_runs"):
        print(f"{t:16}", conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
    print("\nRecent runs:")
    for r in conn.execute("""SELECT r.id, s.slug, r.status, r.rows_loaded, r.started_at::timestamp(0)
                             FROM ingestion_runs r JOIN stores s ON s.id = r.store_id
                             ORDER BY r.id DESC LIMIT 5"""):
        print(" ", r)
    print("\nLatest prices:")
    for r in conn.execute("""SELECT DISTINCT ON (l.id) l.raw_title, p.price_inr, p.observed_at::date
                             FROM price_history p JOIN listings l ON l.id = p.listing_id
                             ORDER BY l.id, p.observed_at DESC LIMIT 8"""):
        print(" ", r)
