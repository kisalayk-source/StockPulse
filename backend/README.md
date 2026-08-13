# StockPulse API

FastAPI backend for manual Alpaca equity/options trading, Finnhub fundamentals, and
lazy-loaded Kronos forecasts. Python 3.12 is recommended.

## Setup

Run commands from the repository root so the existing `model` package remains importable:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt
cd backend
uvicorn app.main:app --reload
```

OpenAPI documentation is available at `http://localhost:8000/docs`.

## Configuration

Create `backend/.env` or export these environment variables:

```dotenv
ALPACA_PAPER_KEY=
ALPACA_PAPER_SECRET=
ALPACA_LIVE_KEY=
ALPACA_LIVE_SECRET=
ALPACA_DATA_FEED=iex
ALPACA_DATA_CREDENTIALS_MODE=paper
FINNHUB_API_KEY=

ALLOW_LIVE_TRADING=false
LIVE_CONFIRMATION_TOKEN=
ALLOW_SHORT_SELLING=false
ALLOW_UNCOVERED_OPTIONS=false
API_KEY=
CORS_ORIGIN=http://localhost:5173
CORS_ORIGIN_REGEX=
FORECAST_RATE_LIMIT_PER_MINUTE=30
FORECAST_SCAN_RATE_LIMIT_PER_MINUTE=10
ORDER_RATE_LIMIT_PER_MINUTE=30

KRONOS_MODEL_ID=NeoQuasar/Kronos-small
KRONOS_TOKENIZER_ID=NeoQuasar/Kronos-Tokenizer-base
KRONOS_DEVICE=auto
KRONOS_MAX_CONTEXT=512
KRONOS_JOURNAL_PATH=backend/data/forecast-journal.jsonl
```

Paper and live credentials are independent. Market-data endpoints use the credential
set selected by `ALPACA_DATA_CREDENTIALS_MODE` (paper by default).
`ALPACA_DATA_FEED` defaults to `iex`, which works with standard paper
accounts; use `sip` only when the account has the corresponding market-data
subscription. `ALLOW_LIVE_TRADING` defaults to false. A live order is accepted only
when it is true and the request body contains a `live_confirmation_token` exactly
matching `LIVE_CONFIRMATION_TOKEN`. Configuration status never returns credentials
or the token.

When `API_KEY` is set, every `/api/v1` request except the liveness endpoint must provide
the value in the `X-API-Key` header. Leaving it empty preserves the local-development default with no
API authentication. Comparisons use a constant-time check. CORS permits only
`CORS_ORIGIN` entries by default; set `CORS_ORIGIN_REGEX` explicitly when LAN browser
origins are required. The PowerShell launcher binds to `127.0.0.1`; set
`KRONOS_API_HOST` only when remote access is intentionally required.

Models are not downloaded during import or application startup. The configured small
model/tokenizer are loaded on the first forecast, put in evaluation mode, and reused.
Set `KRONOS_DEVICE` to `cpu`, `cuda:0`, or another Torch device; `auto` lets Kronos
select CUDA, MPS, or CPU. Forecast context is capped at 512.
`KRONOS_JOURNAL_PATH` optionally persists a bounded JSONL forecast journal used for
live out-of-sample scoring; the default example path is ignored by Git.

## API

All routes use the `/api/v1` prefix.

- `GET /health`
- `GET /ready`
- `GET /config/status`
- `GET /market/clock`
- `GET /symbols/search?q=apple`
- `GET /stocks/{symbol}/overview`
- `GET /stocks/{symbol}/bars?timeframe=1Day&limit=300`
- `GET /account?mode=paper`
- `GET /positions?mode=paper`
- `GET /orders?mode=paper&order_status=open`
- `DELETE /orders/{order_id}`
- `PATCH /orders/{order_id}`
- `GET /options/contracts?underlying=AAPL&mode=paper`
- `GET /options/chain?underlying=AAPL`
- `POST /orders/equity`
- `POST /orders/option`
- `POST /orders/preview`
- `POST /forecast`
- `POST /forecast/movers`
- `GET /forecast/movers/status`

Trading/account requests require an explicit `paper` or `live` mode. Orders are
manual only; this backend contains no scheduler, signal executor, or automatic order
path. Quantity/notional, order type, limit/stop price requirements, time-in-force,
and asset tradability are validated before submission. Provider failures are surfaced
as generic 502 errors and missing configuration as generic 503 errors; detailed causes
are logged server-side. Missing Finnhub values remain `null`; the API does not
synthesize fundamentals. Responses include `X-Request-ID`; logs contain structured
request completion and order-submission audit records without credentials or
confirmation tokens.

Equity sells cannot exceed the current long position unless
`ALLOW_SHORT_SELLING=true`. Option requests accept an optional backward-compatible
`position_intent` (`buy_to_open`, `buy_to_close`, `sell_to_open`, or
`sell_to_close`). If omitted, buys remain `buy_to_open` and sells remain
`sell_to_close`. Closing quantities are checked against current positions, and
`sell_to_open` requires `ALLOW_UNCOVERED_OPTIONS=true`.

Forecast and order routes use lightweight per-process, per-client rate limits. Set a
limit to `0` to disable it. These limits are intentionally local to each API process;
multi-worker deployments should use a shared gateway or rate-limit store.

The movers POST starts a background scan and returns immediately. Poll the status route
for progressive rankings; it returns separate top-50 `gainers` and `losers` lists plus
scan progress, so the UI can render results before the full universe finishes.

Example paper equity order:

```json
{
  "mode": "paper",
  "symbol": "AAPL",
  "side": "buy",
  "type": "limit",
  "time_in_force": "day",
  "qty": 1,
  "limit_price": 190.00
}
```

Forecast presets:

- `short`: 5-minute bars, 256-bar context, 12 forecast bars
- `long`: daily bars, 256-bar context, 20 forecast bars

The request can override `timeframe`, `context`, and `horizon` within schema limits.
Future timestamps skip weekends and keep intraday output inside the US regular session.
This is market-aware but not a full exchange-holiday calendar.

## Tests

```powershell
cd backend
pip install -r requirements-dev.txt
pytest -q
```

Tests use only fakes and HTTP mock transports. They never call Alpaca, Finnhub,
Hugging Face, or submit an order.

## Paper smoke checklist

1. Configure only `ALPACA_PAPER_KEY`, `ALPACA_PAPER_SECRET`, and optionally Finnhub.
2. Keep `ALLOW_LIVE_TRADING=false`.
3. Verify `/health` and `/config/status`; ensure no secrets appear.
4. Search for `AAPL`, open its overview, and request daily bars.
5. Check paper account, positions, and open orders.
6. Inspect an AAPL option contract/chain without submitting.
7. Submit a one-share or low-notional paper order and confirm it in Alpaca.
8. Cancel an open paper order through `DELETE /orders/{order_id}` and verify the broker state.
9. Run a short Kronos forecast; allow time for the first model download/load.
10. Confirm a live request returns 403 while live trading is disabled.

This application is for personal tooling, not investment advice. Broker acceptance
does not guarantee execution, and API-side validation does not replace risk controls.
