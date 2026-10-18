# Price Watch

Search a phone, see its price in every store, how that price has moved, where it may go next,
and the likely reason behind big moves. If a phone is not in the database, it can be looked up
live and tracked from that day.

> **Demo data is simulated.** The prices, the market signals and the live source are generated,
> so the numbers below show that the system works, not what real phones cost. Real sources
> plug in through one adapter file (see [docs/live-search.md](docs/live-search.md)).

<!-- Add screenshots here, for example:
![Product page](docs/screenshots/product.png) -->

## What it does

- **Compare** prices across stores, cheapest first, with search, brand and price filters
- **History** with a chart per store and 30, 90 and 365-day low, high and average
- **Forecast** a likely price range for 7, 14 and 30 days, plus a public accuracy page that tests
  the model against the simple rule "the price stays the same"
- **Reasons** for big price moves (sale windows, memory chip costs, the dollar-rupee rate), each with
  its evidence and a confidence label, and an honest "no clear reason found" when there is none
- **Live search** for phones that are not in the database: matched phones become tracked products,
  unknown phones are shown as "unverified" and kept for review

## How it fits together
| Part | Where | Notes |
|---|---|---|
| Storage | `db/`, `ingestion/` | A price row is saved only when the price changes (about 96% fewer rows than daily snapshots on the 2-year demo set, with no history lost) |
| Matching | `matching/` | Rules plus fuzzy matching for typos; incomplete or unknown titles go to a review queue instead of being guessed |
| Forecast | `forecast/` | 10th, 50th and 90th percentile models per horizon; settings chosen on a validation window before the test period |
| Reasons | `reasons/` | Detects price steps, then matches them with sales and market signals by timing. Evidence, not proof |
| Live search | `live/` | Swappable source, saved answers, daily cap, per-visitor limit, 5 second time limit |
| API | `api/` | FastAPI, see `/docs` when running |
| Website | `web/` | Plain HTML, CSS and JavaScript, served by the API |

## Results on the demo data

Forecast, tested on the last 180 days with the model trained only on earlier data:

| Horizon | Typical miss | "No change" miss | Range held (aim 80%) |
|---|---|---|---|
| 7 days | 1.12% | 1.50% | 88.5% |
| 14 days | 1.23% | 1.70% | 87.1% |
| 30 days | 2.1% | 2.19% | 85.8% |

The forecast helps most when a sale starts or ends inside the period (about 4-5% miss against about
8% for "no change"). In quiet periods it is no better than "no change". The sale calendar is a model
input, as real sales are announced in advance, but the demo data was built with the same calendar,
so real results will be less clean.

Other checks: all 300 demo listings match the right product (an easy test, because the titles come in
three fixed styles, so measure again on real listings); about 70% of detected price moves have an
evidence-backed reason and the rest say so.

## Run it (Windows PowerShell)

You need Python 3.12 and PostgreSQL 16 or 17.

```powershell
git clone https://github.com/Ramcharan1216/price-watch.git
cd price-watch
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env        # first time only: this overwrites any existing .env. Then set your own password in both places
```

Create the database (adjust the PostgreSQL version in the path):

```powershell
$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
& $psql -U postgres -c "CREATE USER priceintel WITH PASSWORD 'yourpassword';"
& $psql -U postgres -c "CREATE DATABASE priceintel OWNER priceintel;"
& $psql -U priceintel -d priceintel -f db\init\001_schema_nodocker.sql
python scripts/check_db.py
```

(With Docker instead: `docker compose up -d` creates everything, including TimescaleDB.)

Load the demo data and build everything:

```powershell
python scripts/migrate.py
python scripts/generate_synthetic_long.py
python ingestion/run_csv.py data/synthetic_long/prices_amazon_in.csv --store amazon_in --date-col date
python ingestion/run_csv.py data/synthetic_long/prices_flipkart.csv --store flipkart --date-col date
python ingestion/run_csv.py data/synthetic_long/prices_croma.csv --store croma --date-col date
python matching/run_matching.py
python scripts/load_signals.py
python forecast/run_forecast.py
python reasons/run_reasons.py
uvicorn api.main:app --reload
```

Open http://127.0.0.1:8000/ for the site and http://127.0.0.1:8000/docs for the API.

## Tests

```powershell
python tests/test_parser.py      # title reading
python tests/test_loader.py      # change-only storage, history replay (database)
python tests/test_forecast.py    # forecast engine
python tests/test_reasons.py     # reason engine
python tests/test_api.py         # API (database, demo data loaded)
python tests/test_live.py        # live pipeline, slow and broken sources (database)
python tests/test_live_api.py    # live endpoint behaviour
```

## Known limits

- All data is simulated. A real source needs an adapter and a key (`live/adapters/template.py`).
- Matching needs a list of known models (`data/models.csv`); unknown models are reviewed, not guessed.
- The live-search limits are kept inside one server process; several servers would need a shared store.
- The memory-cost and rupee signals are simulated; real feeds would replace `scripts/load_signals.py`.

## Roadmap

CI with GitHub Actions, real market-signal feeds, a review screen for unverified matches,
price-drop alerts, and a second product category.
