# Project spec (one page)

## Goal
A site where a user searches an electronic product and sees current prices
across stores, its price history, a forecast range, and a likely reason for
recent price moves.

## v1 scope (ships at end of week 8)
- Category: smartphones only
- Stores: 2 to 3
- Features: search, store comparison, price history with 30/90/365-day stats
- Not in v1: forecasting, reasons, alerts (phases 5 to 7)

## Data source decision (fill this in)
| Store | Source (api / affiliate / scrape / dataset) | Terms checked? | Notes |
|-------|---------------------------------------------|----------------|-------|
|       |                                             |                |       |
|       |                                             |                |       |
|       |                                             |                |       |

Rules: prefer official/affiliate APIs. Scrape only if the site's terms and
robots.txt allow it. Keep a dataset fallback so development is never blocked.

## Success metrics (fill in numbers as you measure them)
- Matching accuracy on 100 hand-labeled pairs: __%
- Daily ingestion success rate: __%
- Forecast error vs baseline (backtest): __
- Big price moves with an evidence-backed reason: __%

## Risks
- Data access changes or gets blocked: keep sources swappable
- Short price history: start collecting early, develop models on a dataset
- Wrong explanations: always show evidence, allow "No clear reason found"
