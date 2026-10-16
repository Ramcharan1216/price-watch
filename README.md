# Price Intel

Electronics price comparison with history, forecasts, and evidence-backed
reasons for price moves. Status: Phase 0 (setup).

## Quick start
```bash
cp .env.example .env          # then edit the password in both places
docker compose up -d
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/check_db.py    # expect: OK: schema is in place
```

## Layout
- `db/init/` SQL schema, runs on first start
- `ingestion/` data collectors (Phase 1)
- `matching/` product matching (Phase 2)
- `api/` FastAPI backend (Phase 3)
- `web/` frontend (Phase 4)
- `docs/spec.md` scope, data sources, metrics

To change the schema during early development, run `make reset`
(this deletes local data).
