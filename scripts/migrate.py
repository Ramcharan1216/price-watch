"""Apply every SQL file in db/migrations/ in order. Safe to run repeatedly."""
import glob
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    for path in sorted(glob.glob("db/migrations/*.sql")):
        with open(path, encoding="utf-8") as f:
            conn.execute(f.read())
        print("applied", path)
