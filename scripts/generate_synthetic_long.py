"""Generate a 2-YEAR SIMULATED price history (not real prices) for forecasting work.

Built in on purpose: slow price erosion as models age, three announced sale windows a
year, random store price moves that fade back, and a memory-cost rise (May to July 2026)
for high-RAM phones that nothing in the model can see. Only price CHANGES are written.
Run from the project folder:  python scripts/generate_synthetic_long.py
"""
import csv, math, os, random, string, sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from forecast.sale_calendar import sale_index

OUT = os.path.join("data", "synthetic_long")
os.makedirs(OUT, exist_ok=True)
START, DAYS = date(2024, 10, 17), 730          # ends 2026-10-16
random.seed(42)

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

DISC = {0: 0.94, 1: 0.93, 2: 0.90}              # Jan, Jun, Oct sale windows
DISC_APPLE = {0: 1.0, 1: 0.99, 2: 0.97}


def cost_factor(ram, day):
    """Memory cost rise, May to mid-July 2026, bigger for high-RAM phones; it then stays."""
    s, e = date(2026, 5, 1), date(2026, 7, 15)
    if day <= s:
        return 1.0
    frac = min(1.0, (day - s).days / (e - s).days)
    return 1 + (0.07 if ram >= 12 else 0.03 if ram >= 8 else 0.0) * frac


listings, truth = [], []
for brand, model, base, variants, colors in CATALOG:
    for i, (ram, sto) in enumerate(variants):
        for color in colors:
            for store in STORES:
                listings.append(dict(store=store, sku=sku(store), brand=brand, model=model, ram=ram, sto=sto,
                                     color=color, title=title(store, brand, model, ram, sto, color),
                                     base=base * (1 + 0.12 * i) * random.uniform(0.97, 1.03)))
                truth.append((store, listings[-1]["sku"], brand, model, ram, sto))

files = {s: csv.writer(open(f"{OUT}/prices_{s}.csv", "w", newline="", encoding="utf-8")) for s in STORES}
for w in files.values():
    w.writerow(["sku", "title", "price", "url", "date"])
rows = 0
for idx, L in enumerate(listings):
    rng = random.Random(7000 + idx)
    apple = L["brand"] == "Apple"
    decay = rng.uniform(-0.0003, -0.0001) if apple else rng.uniform(-0.0006, -0.0002)
    shock, joined, last = 0.0, {}, None
    for t in range(DAYS):
        day = START + timedelta(days=t)
        if rng.random() < 0.012:
            shock += rng.choice([-0.04, -0.025, -0.015, 0.015, 0.025, 0.04])
        shock *= 0.985
        sale, k = 1.0, sale_index(day)
        if k is not None and joined.setdefault((day.year, k), rng.random() < 0.85):
            sale = (DISC_APPLE if apple else DISC)[k]
        price = round_price(L["base"] * math.exp(decay * t + shock) * sale * cost_factor(L["ram"], day))
        if price != last:
            files[L["store"]].writerow([L["sku"], L["title"], price, f"https://example.com/{L['store']}/{L['sku']}", day.isoformat()])
            last, rows = price, rows + 1

with open(f"{OUT}/ground_truth.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["store", "sku", "brand", "model", "ram_gb", "storage_gb"])
    w.writerows(truth)
print(f"{len(listings)} listings, {DAYS} days each, {rows} price changes written")
