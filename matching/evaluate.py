"""Measure matching accuracy against data/synthetic/ground_truth.csv.

  python matching/evaluate.py
Reports coverage (share matched), precision (share of matches that are right)
and overall accuracy. Prints the first mistakes so you can improve the parser.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestion"))
from common import connect  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "data/synthetic/ground_truth.csv"
truth = {(r["store"], r["sku"]): (r["brand"], r["model"], int(r["ram_gb"]), int(r["storage_gb"]))
         for r in csv.DictReader(open(path, encoding="utf-8"))}

rows = connect().execute(
    """SELECT s.slug, l.store_sku, l.raw_title, l.match_status,
              p.brand, p.model, p.ram_gb, p.storage_gb
       FROM listings l JOIN stores s ON s.id = l.store_id
       LEFT JOIN products p ON p.id = l.product_id""").fetchall()

total = matched = correct = 0
wrong, unmatched = [], []
for slug, sku, title, status, *prod in rows:
    key = (slug, sku)
    if key not in truth:
        continue
    total += 1
    if prod[0] is None:
        unmatched.append((title, status))
        continue
    matched += 1
    if tuple(prod) == truth[key]:
        correct += 1
    else:
        wrong.append((title, tuple(prod), truth[key]))

if not total:
    sys.exit("No listings from the ground-truth file found. Load the synthetic data first.")
print(f"Listings checked: {total}")
print(f"Coverage (matched): {matched / total:.1%}")
print(f"Precision (matched and right): {correct / max(matched, 1):.1%}")
print(f"Overall accuracy: {correct / total:.1%}")
for title, got, want in wrong[:8]:
    print("WRONG:", title, "| got", got, "| expected", want)
for title, status in unmatched[:8]:
    print("UNMATCHED:", title, f"({status})")
