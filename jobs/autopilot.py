"""The autopilot: keeps the site's prices, catalog and forecasts up to date by itself.

  python jobs/autopilot.py --once         one cycle now
  python jobs/autopilot.py --every 60     a cycle every 60 minutes until Ctrl+C

Every cycle      refresh prices for the searches people made recently
Once a week      look for new phone models (a few brands per run) and learn the well-evidenced ones
Once a day       link listings to newly learned models, retrain the forecast, redo the "why it moved" reasons

It shares the daily and monthly search limits with the website, so it cannot spend more than you allow.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
from jobs.catalog import mine  # noqa: E402
from live.pipeline import default_cap, default_monthly_cap, default_timeout, refresh_queries  # noqa: E402


def due(name, hours):
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        row = conn.execute("SELECT now() - last_run > make_interval(hours => %s) FROM job_state WHERE name = %s", (hours, name)).fetchone()
        return True if row is None else bool(row[0])
    finally:
        conn.close()


def mark(name, detail=""):
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        conn.execute("INSERT INTO job_state (name, detail) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE "
                     "SET last_run = now(), detail = EXCLUDED.detail", (name, detail))
        conn.commit()
    finally:
        conn.close()


def run_cycle(adapter=None, refresh_limit=5, mine_limit=3, pause=2.0, subprocesses=True):
    """One pass. Returns what ran, so it can be printed and tested."""
    done = {}
    done["refresh"] = refresh_queries(limit=refresh_limit, stale_minutes=60, pause=pause, timeout=default_timeout(),
                                      daily_cap=default_cap(), monthly_cap=default_monthly_cap(), adapter=adapter)
    mark("autopilot:refresh", str(done["refresh"]["refreshed"]))
    if due("autopilot:mine", 24 * 7):
        done["mine"] = mine(limit=mine_limit, adapter=adapter)
        mark("autopilot:mine", ",".join(done["mine"]["brands"]))
    if due("autopilot:daily", 24):
        steps = {}
        if subprocesses:
            for name, args in (("matching", ["matching/run_matching.py", "--redo"]), ("forecast", ["forecast/run_forecast.py"]),
                               ("reasons", ["reasons/run_reasons.py"])):
                r = subprocess.run([sys.executable] + args, cwd=ROOT, capture_output=True, text=True)
                steps[name] = "ok" if r.returncode == 0 else "failed: " + (r.stderr.strip().splitlines() or ["?"])[-1][:120]
        done["daily"] = steps
        mark("autopilot:daily", str(steps))
    return done


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--every", type=int, default=60, help="minutes between cycles")
    p.add_argument("--refresh-limit", type=int, default=5, help="searches to refresh per cycle")
    a = p.parse_args()

    def cycle():
        r = run_cycle(refresh_limit=a.refresh_limit)
        f = r["refresh"]
        extra = "".join(f" | {k}: {v}" for k, v in r.items() if k != "refresh")
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] refreshed {f['refreshed']}/{f['checked']}, new prices {f['new_prices_stored']}"
              + (f" | stopped: {f['stopped']}" if f["stopped"] else "") + extra)

    if a.once:
        cycle()
    else:
        print(f"Autopilot running, a cycle every {a.every} minutes. Press Ctrl+C to stop.")
        try:
            while True:
                cycle()
                time.sleep(a.every * 60)
        except KeyboardInterrupt:
            print("Stopped.")
