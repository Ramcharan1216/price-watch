"""Parser tests, no database needed:  python tests/test_parser.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "matching"))
from title_parser import load_models, parse_title  # noqa: E402

M = load_models(os.path.join(os.path.dirname(__file__), "..", "data", "models.csv"))
CASES = [
    ("Samsung Galaxy S24 5G (Onyx Black, 8GB RAM, 256GB Storage)", ("Samsung", "Galaxy S24", 8, 256)),
    ("SAMSUNG Galaxy S24 5G (Onyx Black, 256 GB)  (8 GB RAM)", ("Samsung", "Galaxy S24", 8, 256)),
    ("Samsung Galaxy S24 8GB 256GB Onyx Black", ("Samsung", "Galaxy S24", 8, 256)),
    ("Samsng Galaxxy S24 8GB 256GB Onyx Black", ("Samsung", "Galaxy S24", 8, 256)),
    ("Redmi Note 13 Pro+ 5G (Fusion Purple, 12GB RAM, 256GB Storage)", ("Redmi", "Note 13 Pro+", 12, 256)),
    ("REDMI Note 13 Pro 5G (Arctic White, 128 GB)  (8 GB RAM)", ("Redmi", "Note 13 Pro", 8, 128)),
    ("Apple iPhone 15 Plus 5G (Pink, 6GB RAM, 256GB Storage)", ("Apple", "iPhone 15 Plus", 6, 256)),
    ("One Plus 12R 8GB 128GB Iron Gray", ("OnePlus", "12R", 8, 128)),
    ("ONEPLUS 12 5G (Flowy Emerald, 512 GB)  (16 GB RAM)", ("OnePlus", "12", 16, 512)),
    ("Nothing Phone (2a) 5G (Black, 8GB RAM, 128GB Storage)", ("Nothing", "Phone (2a)", 8, 128)),
    ("Motorla G84 8GB 256GB Viva Magenta", ("Motorola", "G84", 8, 256)),
]
for title, want in CASES:
    r = parse_title(title, M)
    got = (r["brand"], r["model"], r["ram_gb"], r["storage_gb"])
    assert got == want, f"{title}\n  got  {got}\n  want {want}"

r = parse_title("Apple iPhone 15 (128 GB) - Black", M)
assert r["missing"] == ["ram"], "RAM-less title should be flagged for review"
r = parse_title("Fairphone 5 8GB 256GB Green", M)
assert "brand" in r["missing"], "unknown brand should be flagged"
for title in ["Samsung Galaxy S24 Ultra 5G (Titanium Gray, 12GB RAM, 512GB Storage)",
              "Apple iPhone 15 Pro Max (256 GB) - Natural Titanium"]:
    assert "model" in parse_title(title, M)["missing"], f"unknown variant must go to review: {title}"
print("PASS: parser handles", len(CASES), "title styles, typos, and flags incomplete titles")
