# SEC Accumulation Score

StockPulse ingests public SEC EDGAR filings and produces an explainable **Accumulation Score (0–100)**. The score is a **research signal**, not investment advice or a trading instruction.

## Overview

The accumulation engine combines institutional holdings (13F), beneficial ownership (13D/13G), insider transactions (Form 4), and confirmation from price/volume and fundamentals into a weighted score with an evidence layer. SEC failures degrade gracefully — trading, forecasts, and quotes continue to work.

```text
SEC EDGAR filings
    → normalized events (deduped by accession)
    → component scores (institutional, insider, major holder, price/volume, fundamentals)
    → Accumulation Score 0–100
    → ACCUMULATION | NEUTRAL | DISTRIBUTION
```

Score bands (configurable):

| Range | Label |
|-------|-------|
| 80–100 | Strong Accumulation |
| 60–79 | Accumulation |
| 40–59 | Neutral |
| 20–39 | Distribution |
| 0–19 | Very Strong Distribution |

## Data sources

- SEC EDGAR (`data.sec.gov`, `sec.gov/files/company_tickers.json`)
- No SEC API key required for public endpoints
- Requests identify the application via `SEC_USER_AGENT` (required by SEC fair access policy)
- Default rate limit: 8 requests/second (below SEC 10 req/s guidance)
- Finnhub (extended fundamentals, sector profile) and Alpaca (OHLCV) for confirmation components

## Form caveats

| Form | Meaning | Timing |
|------|---------|--------|
| 13F | Quarterly reported institutional holdings | Available after **filing date**, not period end |
| 13D / 13G | Beneficial ownership disclosures | Activist vs passive context preserved in evidence |
| Form 4 | Insider transaction filings | Filing date may differ from transaction date |

**Good:** “Berkshire reported an increased XOM position in its latest available 13F.”

**Bad:** “Berkshire bought XOM today.”

Insider transaction codes:

| Code | Classification | Counted in accumulation? |
|------|----------------|--------------------------|
| P | Discretionary buy | Yes |
| S | Discretionary sell | Yes |
| A | Compensation / award | No |
| M | Option exercise | No |
| F | Tax withholding | No |

Institutional position changes: `NEW_POSITION`, `INCREASED`, `UNCHANGED`, `DECREASED`, `EXITED` — labeled as **reported institutional position change**, not live trade activity.

## Scoring methodology

Component weights in [`backend/configs/sec_accumulation.yaml`](../backend/configs/sec_accumulation.yaml):

| Component | Default weight |
|-----------|----------------|
| Institutional accumulation | 35% |
| Insider accumulation | 30% |
| Major holder activity | 15% |
| Price/volume confirmation | 10% |
| Fundamental confirmation | 10% |

Institutional signal weights (`new_position`, `increased`, `decreased`, `exited`, etc.) and insider cluster rules (`window_days`, `min_insiders`) are also in that file. Missing confirmation data renormalizes weights; the overall score stays bounded 0–100.

## Configuration

Add to `backend/.env` (see [`backend/.env.example`](../backend/.env.example)):

```dotenv
SEC_USER_AGENT=StockPulse contact@example.com
SEC_ENABLED=true
SEC_REQUESTS_PER_SECOND=8
SEC_CACHE_TTL_SECONDS=3600
SEC_SCORE_CONFIG_PATH=backend/configs/sec_accumulation.yaml
SEC_RATE_LIMIT_PER_MINUTE=60
SEC_SCAN_UNIVERSE_CAP=100
SEC_SCAN_ON_STARTUP=false

# Optional AI research narration (structured data only; never invent tickers/scores)
RESEARCH_LLM_ENABLED=false
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-4o-mini
```

Set `SEC_USER_AGENT` to a string that includes your app name and a contact email before fetching live EDGAR data.

## API endpoints

All routes use the `/api/v1` prefix and require authentication when JWT/API-key auth is enabled.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/stocks/{symbol}/sec` | Full SEC intelligence (score, components, institutional/insider/major-holder activity, caveats) |
| GET | `/stocks/{symbol}/institutional` | 13F position changes |
| GET | `/stocks/{symbol}/insiders` | Classified Form 4 transactions |
| GET | `/stocks/{symbol}/accumulation` | Score, components, events, history, `as_of` |
| GET | `/stocks/{symbol}/filings` | Recent SEC filings (`months`, `limit`) with insider/ownership detail |
| GET | `/sectors` | Normalized sector list with ticker counts |
| GET | `/sectors/{sector}/accumulation` | Sector averages and per-ticker scores |
| GET | `/accumulation/top` | Ranked stocks (`sector`, `min_score`, `limit` query params) |
| POST | `/accumulation/scan` | Start background blue-chip + movers universe scan |
| GET | `/accumulation/scan/status` | Scan progress (`scanned`, `total`, `status`) |
| POST | `/research/query` | Natural-language research query → filters, ranked candidates, narrative |

Example accumulation response shape:

```json
{
  "ticker": "XOM",
  "score": 84,
  "signal": "ACCUMULATION",
  "classification": "STRONG_ACCUMULATION",
  "components": {
    "institutional": 88,
    "insider": 76,
    "major_holder": 81,
    "price_volume": 79,
    "fundamentals": 86
  },
  "events": [],
  "history": [{"date": "2026-05-01", "score": 84, "classification": "STRONG_ACCUMULATION"}],
  "as_of": "2026-09-01T14:00:00+00:00"
}
```

SEC provider errors appear in `provider_errors` without breaking other dashboard features.

## Dashboard UI

On the **Market** tab, each symbol shows an **SEC & Ownership Intelligence** panel: overall score, component bars, accumulation trend, recent institutional and insider activity, and filing caveats.

Additional dashboard tabs:

- **Sectors** — average accumulation score, % increasing/decreasing by sector, top tickers per sector (populated by market scan)
- **Top Accumulation** — filterable ranked list across scanned universe
- **SEC Records** — compact ticker search; filings from the last 6 months with **filing entity**, **action** (bought/sold/new investment), EDGAR links, AI analysis card (sentiment + gist), and stat chips (syncs on tab open and search)
- **AI Research** — query box with candidate table, structured filters, and evidence-backed results (optional LLM narration)

Signal columns use human-readable classification labels (e.g. **Strong Accumulation**, **Distribution**) rather than raw enum strings.

## Market scan

On login the dashboard starts a background **accumulation scan** that merges the blue-chip universe with current Alpaca movers (up to `SEC_SCAN_UNIVERSE_CAP`, default 100). Each ticker is synced from EDGAR and scored into SQLite. Sectors and Top Accumulation read from this cache — they are not limited to the active Market symbol.

Configure:

```dotenv
SEC_SCAN_UNIVERSE_CAP=100
SEC_SCAN_ON_STARTUP=false
```

The scan runs in a background thread. Universe construction (blue-chip list + cached Alpaca movers) and per-ticker EDGAR sync/scoring happen off the API request path so routes like `/sectors` return immediately. Progress is available at `GET /accumulation/scan/status`. The UI shows a scan progress banner on Sectors, Top Accumulation, and AI Research tabs.

When fewer than 10 tickers are scored, the first call to `/sectors` or `/accumulation/top` may auto-start a scan if one is not already running.

Sector names from Finnhub are normalized to dashboard buckets (e.g. `Financial Services` → `Financials`, `Information Technology` → `Technology`) before aggregation.

## AI research

`POST /research/query` parses sector and accumulation keywords into structured filters, runs a short mini-scan when needed, ranks candidates from the score cache, and returns a **candidate table** plus template narrative. Thresholds are adaptive (with fallback to best available matches when filters are strict). When `RESEARCH_LLM_ENABLED=true`, an OpenAI-compatible model may narrate over the injected JSON context only — it must not invent tickers, scores, or filings.

## SEC Records tab

`GET /stocks/{symbol}/filings?months=6&limit=100` syncs the issuer from EDGAR when needed, then returns filings in the date window plus related Form 4 insider lines and 13D/G beneficial ownership rows. Each filing includes:

| Field | Description |
|-------|-------------|
| `filer_name` | Insider, institution, or beneficial owner who filed |
| `action` | Human-readable activity (e.g. Bought 10,000 shares, New investment, New major holder) |
| `action_tone` | `positive`, `negative`, or `neutral` for UI coloring |
| `edgar_url` | SEC archive link when CIK mapping is available |

`GET /stocks/{symbol}/filings/analysis?months=6` reads from SQLite only (no re-sync) and returns an AI-powered or rule-based summary:

```json
{
  "ticker": "AAPL",
  "headline": "Recent SEC activity for AAPL looks mostly positive.",
  "gist": ["2 Form 4 filings since ...", "Insider activity skews positive."],
  "sentiment": "good",
  "sentiment_label": "Good news",
  "highlights": [{"category": "insider", "text": "1 insider buy", "tone": "positive"}],
  "source": "rules",
  "disclaimer": "..."
}
```

When `RESEARCH_LLM_ENABLED=true` and `OPENAI_API_KEY` is set, analysis uses the same OpenAI-compatible chat API as `/research/query`; otherwise a deterministic rule-based fallback scores insider buys/sells, institutional changes, and accumulation score.

The dashboard loads filings first, then fetches analysis in a separate request so the table is not blocked by LLM latency.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| **502** on `/api/v1/*` through the UI | Frontend proxy could not reach the API on `127.0.0.1:8000` (startup race or API down) | Confirm backend is listening: `http://127.0.0.1:8000/api/v1/health`. Re-run `scripts/publish-kronos-lan.ps1`. |
| Sectors / Top show one ticker (e.g. SPY) or stay empty | Score cache not populated yet | Wait for scan progress to finish; use dashboard **Refresh** or `POST /accumulation/scan`. |
| AI Research returns no candidates | Scan still running or strict filters | Wait for scan; try a broader query (e.g. “top accumulation stocks”). |
| SEC Records empty for a valid ticker | EDGAR sync still running, no filings in the last N months, or `SEC_ENABLED=false` | Wait for the loading state to finish; confirm `SEC_USER_AGENT` and network; check `provider_errors` in the response. Re-search the ticker to trigger a fresh sync. |

SQLite uses WAL mode so the background scan and live API reads can overlap safely.

## Code layout

```text
backend/app/sec/
    client.py          SEC HTTP client (throttle, cache)
    scan.py            Background accumulation scan (universe + progress)
    sectors.py         Finnhub → dashboard sector normalization
    submissions.py     Ticker ↔ CIK mapping
    service.py         Ingestion orchestrator + filing enrichment (entity/action)
    forms/             13F, 13D, 13G, Form 4 parsers
    engines/           Scoring (institutional, insider, major holder, confirmation)
    backtest/          Look-ahead-safe accumulation backtest
    db_models.py       SQLite persistence
backend/app/services/
    filings_analysis.py  SEC Records AI/rule-based analysis
    openai_client.py       Shared OpenAI chat helper (research + filings)
backend/configs/sec_accumulation.yaml
backend/scripts/sec_backtest.py
```

## Anti double-counting

Pipeline: SEC filing → normalized event → component feature → component score → overall score. Each event has a stable `event_id` and SEC accession number; amendments supersede prior filings.

## Backtesting

Offline accumulation backtest (separate from `kronos_backtest`):

```bash
cd backend
python scripts/sec_backtest.py XOM --days 365
```

The runner enforces `filing_date <= as_of_date` so 13F data is not treated as available before publication. Compare forward returns (1M/3M/6M/1Y) across high accumulation, neutral, and high distribution buckets.

See also [BACKTEST.md](./BACKTEST.md#sec-accumulation-backtest).

## Tests

```bash
cd backend
pytest -q tests/test_sec_*.py tests/test_research_query.py
```

Fixtures live under `backend/tests/fixtures/sec/`. Tests use HTTP mock transports and fixture XML — no live SEC or broker calls.

## Limitations

- 13F data is quarterly and lagged; never imply real-time institutional trading
- CUSIP→ticker mapping may be incomplete for some issuers
- SEC outages degrade SEC panels without breaking trading or forecasts
- Accumulation scores are one input to research — not probabilities of future returns
