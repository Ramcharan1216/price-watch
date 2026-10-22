# Real prices, new phones, and the autopilot

## What this adds
- **A real price source:** Google Shopping through SerpApi (`LIVE_SOURCE=serpapi`).
- **A catalog that finds new phones itself:** it reads real listings, works out each phone's brand and model,
  and approves a model automatically only when several listings from several stores agree.
- **An autopilot** that keeps prices fresh, learns new models, retrains the forecast and redoes the "why it moved" reasons.
- **An honest header:** it says "Demo data" for simulated prices and "Live prices, updated X ago" for real ones.

## 1. Get a key and turn it on
Create a SerpApi account (it has a free plan; check serpapi.com/pricing for its monthly size, because sources
disagree between 100 and 250 searches). Copy your key into `.env`:
```
LIVE_SOURCE=serpapi
SERPAPI_KEY=your-key-here             # never commit this; .env is ignored by git
LIVE_DAILY_CAP=20
LIVE_MONTHLY_CAP=100                  # set this to your plan's size; nothing is called once it is used up
```
Optional: `SERPAPI_LOCATION=Mumbai, Maharashtra, India`, and `SERPAPI_DEBUG=1` to save the raw answer to
`data/raw/serpapi_last_response.json` (not committed) if results look wrong.

## 2. Switch from simulated to real data
```
python scripts/migrate.py
python scripts/reset_data.py --yes        # deletes the SIMULATED data (your learned catalog is kept)
python jobs/catalog.py seed               # searches each brand once: keeps listings and prices, learns models, links them
```
`seed` uses about one search per brand. Run `python jobs/catalog.py list` to see what it learned.
Start the site and the header should now say "Live prices".

## 3. Run the autopilot
```
python jobs/autopilot.py --every 60
```
Every cycle it refreshes prices for searches people made recently. Once a week it looks for new models (3 brands per run).
Once a day it links listings to newly learned models, retrains the forecast and redoes the reasons.
It shares the daily and monthly limits with the website, so it can never spend more than you allow.

## What to expect (be realistic)
- **A free plan is small.** Seeding about 13 brands uses a seventh of 100 searches. Plan on roughly 2 refreshed
  searches a day afterwards. More frequent updates need a paid plan.
- **Forecasts start empty.** A forecast needs about 120 days of prices per phone. Until then the page says how many days it has.
  A source of past prices would fix this; one exists for Amazon (not checked for India), so ask before relying on it.
- **New phones appear when listings show them.** The discovery job reads names from shopping results, so a phone
  appears once stores list it. A model needs 3 listings from 2 stores to be approved automatically.
- **Check what it learns.** `python jobs/catalog.py list`, then `reject "Brand" "Model"` for a wrong guess. Rejections stick.
- **Appliances:** search works for any product, but matching understands phones only, so appliances show as "unverified".

## Limits
- Not yet run against the live SerpApi service in this project's tests (they use answers in the documented format).
  The first real run may need small changes. Turn on `SERPAPI_DEBUG=1` and keep the file.
- Google Shopping links open Google's page listing all sellers, not one store's own page.
- Prices are what Google Shopping shows, which can lag the store by hours.
