"""Generate SIMULATED phone listings and price history for 3 stores.
Not real prices. Purpose: build and test matching, history and forecasting.
Reproducible (fixed seed). Run from the project folder:
  python scripts/generate_synthetic.py
Writes data/synthetic/prices_<store>.csv and data/synthetic/ground_truth.csv
"""
import csv, os, random, string
from datetime import date, timedelta

random.seed(42)
OUT = "data/synthetic"
os.makedirs(OUT, exist_ok=True)
START, DAYS = date(2026, 9, 1), 45

# brand, model, base price INR (simulated), [(ram, storage)], colors
CATALOG = [
 ("Samsung","Galaxy S24",74999,[(8,128),(8,256)],["Onyx Black","Marble Gray"]),
 ("Samsung","Galaxy A55",39999,[(8,128),(8,256)],["Awesome Navy","Awesome Lilac"]),
 ("Samsung","Galaxy M35",19999,[(6,128),(8,128)],["Moonlight Blue","Dark Blue"]),
 ("Apple","iPhone 15",69900,[(6,128),(6,256)],["Black","Blue"]),
 ("Apple","iPhone 15 Plus",79900,[(6,128),(6,256)],["Pink","Green"]),
 ("Apple","iPhone 14",56900,[(6,128)],["Midnight","Starlight"]),
 ("OnePlus","12",64999,[(12,256),(16,512)],["Flowy Emerald","Silky Black"]),
 ("OnePlus","12R",39999,[(8,128),(16,256)],["Iron Gray","Cool Blue"]),
 ("OnePlus","Nord CE4",24999,[(8,128),(8,256)],["Celadon Marble","Dark Chrome"]),
 ("Redmi","Note 13 Pro",25999,[(8,128),(8,256)],["Arctic White","Midnight Black"]),
 ("Redmi","Note 13 Pro+",31999,[(8,256),(12,256)],["Fusion Purple","Fusion Black"]),
 ("Redmi","Note 13",16999,[(6,128),(8,128)],["Stealth Black","Prism Gold"]),
 ("Xiaomi","14",69999,[(12,256)],["Jade Green","Black"]),
 ("Realme","12 Pro",26999,[(8,128),(8,256)],["Submarine Blue","Navigator Beige"]),
 ("Realme","Narzo 70 Pro",19999,[(8,128),(8,256)],["Glass Green","Glass Gold"]),
 ("Vivo","V30",33999,[(8,128),(8,256)],["Andaman Blue","Peacock Green"]),
 ("Vivo","T3",19999,[(6,128),(8,128)],["Cosmic Blue","Crystal Flake"]),
 ("Oppo","Reno 11",29999,[(8,128),(8,256)],["Wave Green","Rock Grey"]),
 ("Oppo","F25 Pro",23999,[(8,128),(8,256)],["Lava Red","Ocean Blue"]),
 ("Google","Pixel 8a",52999,[(8,128),(8,256)],["Obsidian","Bay"]),
 ("Nothing","Phone (2a)",23999,[(8,128),(12,256)],["Black","White"]),
 ("Motorola","Edge 50 Fusion",22999,[(8,128),(12,256)],["Forest Blue","Hot Pink"]),
 ("Motorola","G84",15999,[(8,128),(8,256)],["Viva Magenta","Midnight Blue"]),
 ("iQOO","Neo 9 Pro",34999,[(8,128),(12,256)],["Conqueror Black","Fiery Red"]),
 ("Poco","X6 Pro",24999,[(8,256),(12,512)],["Racing Grey","Spectre Black"]),
 ("Poco","M6",9999,[(4,128),(6,128)],["Orion Blue","Polaris Green"]),
]
STORES = ["amazon_in", "flipkart", "croma"]
TYPOS = [("Samsung","Samsng"),("Galaxy","Galaxxy"),("iPhone","iPhne"),("OnePlus","One Plus"),
         ("Realme","Realmi"),("Motorola","Motorla")]

def title(store, brand, model, ram, sto, color):
    if store == "amazon_in":
        return f"{brand} {model} 5G ({color}, {ram}GB RAM, {sto}GB Storage)"
    if store == "flipkart":
        return f"{brand.upper()} {model} 5G ({color}, {sto} GB)  ({ram} GB RAM)"
    t = f"{brand} {model} {ram}GB {sto}GB {color}"          # croma
    if random.random() < 0.12:
        a, b = random.choice(TYPOS); t = t.replace(a, b, 1)
    return t

def sku(store):
    c = string.ascii_uppercase + string.digits
    if store == "amazon_in": return "B0" + "".join(random.choices(c, k=8))
    if store == "flipkart":  return "MOB" + "".join(random.choices(c, k=13))
    return str(random.randint(200000, 299999))

def round_price(p):  return int(round(p / 1000.0)) * 1000 - 1

listings, truth = [], []
for brand, model, base, variants, colors in CATALOG:
    for i, (ram, sto) in enumerate(variants):
        variant_price = base * (1 + 0.12 * i)
        for color in colors:
            for store in STORES:
                listings.append(dict(store=store, sku=sku(store), brand=brand, model=model,
                    ram=ram, sto=sto, color=color,
                    title=title(store, brand, model, ram, sto, color),
                    base=variant_price * random.uniform(0.97, 1.03),
                    drift=random.choice([0, 0, 0, 0.0008, -0.0006])))
                truth.append((store, listings[-1]["sku"], brand, model, ram, sto))

files = {s: csv.writer(open(f"{OUT}/prices_{s}.csv", "w", newline="", encoding="utf-8")) for s in STORES}
for w in files.values(): w.writerow(["sku", "title", "price", "url", "date"])
SALE = (date(2026, 10, 1), date(2026, 10, 8))        # simulated festival sale window
n = 0
for L in listings:
    price, level = L["base"], 1.0
    for d in range(DAYS):
        day = START + timedelta(days=d)
        level *= 1 + L["drift"]
        if random.random() < 0.06:                    # occasional real price change
            level *= random.choice([0.97, 0.95, 1.03, 1.02, 0.92])
        sale = 0.90 if SALE[0] <= day <= SALE[1] and L["brand"] in ("Samsung","OnePlus","Redmi","Realme") else 1.0
        price = round_price(L["base"] * level * sale)
        files[L["store"]].writerow([L["sku"], L["title"], price, f"https://example.com/{L['store']}/{L['sku']}", day.isoformat()])
        n += 1

with open(f"{OUT}/ground_truth.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["store", "sku", "brand", "model", "ram_gb", "storage_gb"]); w.writerows(truth)
print(f"{len(listings)} listings, {n} daily observations, {len(CATALOG)} models")
