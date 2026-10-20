# AI research and scheduled refresh

## What you get
- **Search any phone or appliance.** If it is not in the database, the page offers "Check live prices online".
  With `LIVE_SOURCE=ai_web`, Claude searches the web, and the page shows what it found, its sources, and the offers.
- **Prices that keep changing.** `jobs/refresh_prices.py` re-asks the source for searches people made recently,
  most-searched first, and saves a new price only when it changed.
- **Links that work.** Real listing links are used as they are. The simulated demo data has no real links, so its
  "View" buttons open a search on the store and say so.

## Turn on AI research (.env)
```
LIVE_SOURCE=ai_web
ANTHROPIC_API_KEY=your-key-here        # never commit this; .env is already ignored by git
ANTHROPIC_MODEL=claude-sonnet-5-5      # must be a model that supports web search (check the docs)
AI_MAX_SEARCHES=4                      # searches per question; each one is billed
LIVE_DAILY_CAP=20                      # calls per day, shared by the website and the refresh job
LIVE_TIMEOUT=90                        # seconds to wait for one research
```
An administrator of your Anthropic account must enable web search in the Claude Console.
Web search is billed per search plus normal token costs, so keep the daily cap low until you see real usage.
Restart the server after changing `.env`. To go back to the demo source, set `LIVE_SOURCE=fake`.

Optional: `AI_ALLOWED_DOMAINS=amazon.in,flipkart.com,croma.com` limits where it looks. `AI_DEBUG=1` saves the raw
reply to `data/raw/ai_last_response.json` (not committed) so a problem can be diagnosed.

## What keeps it honest
- A link is kept only if a search actually returned it. Invented links are dropped.
- A price is **confirmed** only if the number appears in the text Claude quoted from that same page.
- Confirmed offers are saved to price history (tagged `ai_web`). Unconfirmed ones are shown in a separate
  warned box and are **never saved**, so they cannot create fake price moves or forecasts.
- Sources are always shown next to the answer.

## Limits
- The AI source has not been run against the live service in this project's tests (they use answers in the
  documented format). The first real run may need small prompt changes. Turn on `AI_DEBUG=1` and send the file.
- Store pages may not be readable through web search, so some stores may not appear.
- Research is slower (up to a minute) and costs money per question. For prices you need every hour,
  a structured shopping or affiliate source is cheaper and steadier. Write it as another adapter.

## Keep prices fresh
```
python jobs/refresh_prices.py --once        # refresh now
python jobs/refresh_prices.py --every 60    # repeat every 60 minutes (Ctrl+C to stop)
```
It uses the same daily cap as the website, so it can never spend more than you allowed.
To run it on a schedule in Windows (once an hour), see the command in the project README or ask for it.
