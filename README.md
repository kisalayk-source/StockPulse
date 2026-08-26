# StockPulse

Paper-first trading workstation for US equities and single-leg options. Forecasts, charts, news, portfolio, and manual order tickets in one dashboard — wired to Alpaca and powered by Kronos path forecasts.

**Not investment advice.** Forecasts are research overlays only. Orders are always manual and never placed by the model.

## Features

- **Market workspace** — symbol search, session clock, quote, fundamentals, OHLC chart
- **Forecasts** — Kronos (single model) or ensemble overlay; short / long horizons; path turns and decision context
- **Sentiment & news** — public news sentiment plus investor/regime cues; merged news feed
- **Movers scan** — background scan of blue-chip names for predicted gainers and losers (display-only)
- **Portfolio** — open positions, open/realized P/L, hold ideas from the movers scan
- **Manual trading** — equity and single-leg options tickets with risk preview and review-before-send
- **Paper / live** — paper by default; live requires separate keys, server flag, and typing `LIVE`

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React, TypeScript, Vite (`frontend/`) |
| Backend | FastAPI, uvicorn (`backend/`) |
| Broker / data | Alpaca (bars + trading), Finnhub (fundamentals, news, public sentiment) |
| Forecasts | Kronos (`NeoQuasar/Kronos-small`) and optional ensemble under `forecasting/` |

## Quick start

### Prerequisites

- Python **3.10–3.12**
- Node **22+**
- Alpaca paper API keys (live keys only if you intentionally enable live trading)
- Optional: Finnhub API key for fundamentals / public sentiment

### Configure

```powershell
copy backend\.env.example backend\.env
copy frontend\.env.example frontend\.env.local
```

Edit `backend/.env` with at least:

```dotenv
ALPACA_PAPER_KEY=...
ALPACA_PAPER_SECRET=...
ALPACA_DATA_FEED=iex
ALLOW_LIVE_TRADING=false
FINNHUB_API_KEY=...
CORS_ORIGIN=http://localhost:5173
```

Keep `ALLOW_LIVE_TRADING=false` until paper mode is validated. Use `sip` only with an Alpaca SIP subscription.

### Run (development)

Backend (repo root):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt
cd backend
uvicorn app.main:app --reload
```

Frontend (second terminal):

```powershell
cd frontend
npm ci
npm run dev
```

- App: [http://localhost:5173](http://localhost:5173)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Publish on your LAN

Builds the frontend and starts API + UI (backend stays on loopback; LAN clients use the UI proxy):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/publish-kronos-lan.ps1
```

### Docker

```bash
docker compose up --build
```

Same ports: UI `5173`, API `8000`.

## Safety

- Forecasts never submit orders; the ticket is the only path to the broker
- Every order goes through a review dialog
- Live mode needs live Alpaca credentials, `ALLOW_LIVE_TRADING=true`, and typing **`LIVE`** when switching modes and confirming orders
- Short selling and uncovered option writes stay off unless enabled server-side
- Automated tests use provider fakes and never hit a live brokerage account

## Repository layout

```text
backend/           FastAPI service (Alpaca, Finnhub, Kronos, risk)
frontend/          React dashboard
forecasting/       Optional multi-model forecast adapters
scripts/           Start / LAN publish helpers
docs/              Product & development guides
model/             Kronos model / tokenizer implementation
kronos_backtest/   Historical backtester (not used by the live dashboard)
```

## Docs

| Doc | Contents |
|-----|----------|
| [TRADING_APP.md](./TRADING_APP.md) | StockPulse setup & safety notes |
| [backend/README.md](./backend/README.md) | API, config, smoke checklist |
| [frontend/README.md](./frontend/README.md) | Dashboard commands & API client |
| [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) | Environments, checks, Docker |
| [docs/StockPulse.html](./docs/StockPulse.html) | Product & operations guide |
| [CHANGELOG.md](./CHANGELOG.md) | Release notes |

## License

MIT — see [LICENSE](./LICENSE). Kronos model weights and research artifacts remain attributed to their upstream authors (see Hugging Face model cards).
