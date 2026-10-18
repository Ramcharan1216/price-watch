"""Load SIMULATED market signals (not real data) for the demo:
  dram_index  memory chip price index, rises about 25% from March to mid-June 2026
  usd_inr     dollar-rupee rate, a slow drift with no effect on prices
Real versions would come from market-data providers. Safe to run again.
   python scripts/load_signals.py"""
import json
import os
import random
from datetime import date, timedelta

import psycopg
from dotenv import load_dotenv

load_dotenv()
START, DAYS = date(2024, 10, 17), 730
rng = random.Random(11)
rows, level, fx = [], 100.0, 83.6
for t in range(DAYS):
    day = START + timedelta(days=t)
    level *= 1 + rng.gauss(0, 0.002)
    ramp = min(1.0, max(0.0, (day - date(2026, 3, 1)).days / 106)) * 0.25
    fx += 4.6 / DAYS + rng.gauss(0, 0.04)
    rows.append(("dram_index", "smartphone", day, round(level * (1 + ramp), 2), json.dumps({"unit": "index"}), "simulated"))
    rows.append(("usd_inr", None, day, round(fx, 3), json.dumps({"unit": "INR per USD"}), "simulated"))
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute("DELETE FROM signals WHERE source = 'simulated'")
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO signals (kind, category, observed_on, value, detail, source) "
                        "VALUES (%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING", rows)
print(f"Loaded {len(rows)} simulated signal rows")
