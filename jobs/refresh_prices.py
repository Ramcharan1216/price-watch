"""Keep tracked prices fresh.

  python jobs/refresh_prices.py --once          refresh now, then stop
  python jobs/refresh_prices.py --every 60      repeat every 60 minutes until you press Ctrl+C

It re-asks the price source for searches people made in the last 30 days, most-searched first,
and saves a new price row only when a price changed. It uses the same daily limit as the website
(LIVE_DAILY_CAP), so it can never spend more than you allowed.
"""
import argparse
import os
import sys
import time
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
from live.pipeline import default_cap, default_timeout, refresh_queries  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--once", action="store_true")
p.add_argument("--every", type=int, default=60, help="minutes between runs")
p.add_argument("--limit", type=int, default=10, help="most searches to refresh per run")
p.add_argument("--stale", type=int, default=60, help="only refresh searches older than this many minutes")
p.add_argument("--pause", type=float, default=2.0, help="seconds to wait between calls to the source")
a = p.parse_args()


def run():
    r = refresh_queries(limit=a.limit, stale_minutes=a.stale, pause=a.pause, timeout=default_timeout(), daily_cap=default_cap())
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] checked {r['checked']}, refreshed {r['refreshed']}, "
          f"failed {r['failed']}, new prices {r['new_prices_stored']}" + (f" | stopped: {r['stopped']}" if r["stopped"] else ""))


if a.once:
    run()
else:
    print(f"Refreshing every {a.every} minutes. Press Ctrl+C to stop.")
    try:
        while True:
            run()
            time.sleep(a.every * 60)
    except KeyboardInterrupt:
        print("Stopped.")
