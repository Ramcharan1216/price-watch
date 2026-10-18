# How live search works

```
user searches a phone  ->  our database has it?  yes -> show it (as before)
                                                  no  -> button: "Check live prices online"
user clicks the button ->  saved answer under 10 minutes old?  yes -> use it
                           daily quota left?                  no  -> friendly message
                           ask the price source (5 second limit)
                           read each title -> brand, model, RAM, storage   (matching/title_parser.py)
                           matched phone   -> a real product, tracked from today
                           unknown phone   -> "Unverified match", saved for review
                           show the groups, cheapest first
```

## Files
| File | Job |
|---|---|
| `live/adapters/base.py` | The contract: what a price source must return |
| `live/adapters/fake.py` | A pretend source, so everything works without a key |
| `live/adapters/template.py` | Where YOUR real source goes |
| `live/adapters/__init__.py` | Chooses the source from `LIVE_SOURCE` in `.env` |
| `live/pipeline.py` | The steps above |
| `api/main.py` (`/live-search`) | The web address the page calls, with a per-visitor limit |
| `web/app.js` (`liveHtml`, `runLive`) | The button and the results |
| `tests/test_live.py` | Checks the pipeline, including slow and broken sources |

## Settings (optional, in .env)
```
LIVE_SOURCE=fake        # fake | template | your own
LIVE_DAILY_CAP=200      # most calls to the source per day
LIVE_TIMEOUT=5          # seconds to wait for the source
```

## Why each protection exists
- **Button, not automatic:** a source usually has a daily quota. Typing must not spend it.
- **Saved answers (10 minutes):** the same question twice costs one call.
- **Daily cap:** the quota is never exceeded, even if someone hammers the site.
- **Per-visitor limit (6 a minute):** one person cannot use everyone's share.
- **Time limit:** a slow source cannot freeze the page.
- **Unverified label:** we never claim two listings are the same phone unless the title reader is sure.

## Plugging in a real source
Copy the steps at the top of `live/adapters/template.py`. Only that file changes.
