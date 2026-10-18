"""Match unmatched listings to products.

  python matching/run_matching.py            # only listings not matched yet
  python matching/run_matching.py --redo     # re-match everything except manual matches

Complete, confident parses link the listing to a product (created if new).
Anything incomplete or low-confidence is marked 'review' and left unlinked.
"""
import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion"))
from common import connect  # noqa: E402
from title_parser import AUTO_THRESHOLD, load_models, parse_title  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--models", default="data/models.csv")
p.add_argument("--redo", action="store_true")
a = p.parse_args()

models = load_models(a.models)
conn = connect()
where = "match_status <> 'manual'" if a.redo else "match_status = 'unmatched'"
listings = conn.execute(f"SELECT id, raw_title FROM listings WHERE {where}").fetchall()

counts, reasons = Counter(), Counter()
for listing_id, title in listings:
    r = parse_title(title, models)
    if not r["missing"] and r["confidence"] >= AUTO_THRESHOLD:
        name = f'{r["brand"]} {r["model"]} ({r["ram_gb"]}GB/{r["storage_gb"]}GB)'
        product_id = conn.execute(
            """INSERT INTO products (brand, model, ram_gb, storage_gb, canonical_name)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (brand, model, ram_gb, storage_gb)
               DO UPDATE SET brand = EXCLUDED.brand RETURNING id""",
            (r["brand"], r["model"], r["ram_gb"], r["storage_gb"], name)).fetchone()[0]
        conn.execute("UPDATE listings SET product_id=%s, match_confidence=%s, match_status='auto' "
                     "WHERE id=%s", (product_id, r["confidence"], listing_id))
        counts["auto"] += 1
    else:
        conn.execute("UPDATE listings SET product_id=NULL, match_confidence=%s, match_status='review' "
                     "WHERE id=%s", (r["confidence"], listing_id))
        counts["review"] += 1
        reasons["missing " + ",".join(r["missing"]) if r["missing"] else "low confidence"] += 1
conn.commit()

print(f"Looked at {len(listings)} listings: {counts['auto']} matched, {counts['review']} sent to review")
for reason, n in reasons.most_common():
    print(f"  review reason: {reason} ({n})")
print("Products in catalog:", conn.execute("SELECT count(*) FROM products").fetchone()[0])
