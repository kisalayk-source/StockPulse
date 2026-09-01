# StockPulse

The trading app is split into:

- `backend/`: FastAPI, Alpaca market/trading APIs, Finnhub fundamentals, SEC EDGAR accumulation, and Kronos forecasts
- `frontend/`: React/TypeScript dashboard

The legacy Flask demo in `webui/` remains unchanged.

## Configure

Copy `backend/.env.example` to `backend/.env` and add the relevant credentials.
Paper and live Alpaca credentials are separate. Keep:

```dotenv
ALLOW_LIVE_TRADING=false
LIVE_CONFIRMATION_TOKEN=
API_KEY=
ALPACA_DATA_FEED=iex
SEC_USER_AGENT=StockPulse contact@example.com
SEC_ENABLED=true
```

until paper-mode validation is complete. Before intentional network access, set a
strong `API_KEY`, configure the frontend environment, and restrict CORS and firewall
rules. Use `sip` only with an Alpaca SIP data subscription. Set `SEC_USER_AGENT` to
your app name and contact email before fetching live SEC data (no SEC API key required).
Secrets remain in `backend/.env`, which is ignored by Git. The current personal-app live confirmation
flow uses the literal `LIVE`; API authentication and network controls provide the
actual access boundary.

Score weights for the Accumulation Score live in `backend/configs/sec_accumulation.yaml`.

## Run

Backend, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend, in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. API documentation is at
`http://localhost:8000/docs`.

Use dashboard tabs for **Market** (symbol workspace + SEC Intelligence panel), **Sectors**, **Top Accumulation**, **SEC Records**, and **AI Research**. The first load may take a few minutes while the server scans blue-chip and mover tickers from EDGAR.

Optional scan tuning in `backend/.env`:

```dotenv
SEC_SCAN_UNIVERSE_CAP=100
SEC_SCAN_ON_STARTUP=false
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| **502** on API calls through the UI | Backend not reachable on loopback `:8000`. Restart with `scripts/publish-kronos-lan.ps1` (starts API before frontend). Check `runtime-logs/backend.stderr.log`. |
| Sectors / Top empty or only SPY | Accumulation scan still running — wait for progress banner or call `POST /api/v1/accumulation/scan`. |
| SEC Records empty | EDGAR sync still running, no filings in the last 6 months, or invalid `SEC_USER_AGENT`. Re-search after sync completes; check API `provider_errors`. |

See [docs/SEC_ACCUMULATION.md](./docs/SEC_ACCUMULATION.md#troubleshooting) for SEC-specific detail.

## Safety

- Kronos forecasts and SEC accumulation scores are display-only and cannot submit orders.
- Accumulation scores are research signals, not probabilities of future returns.
- Every order requires a review dialog.
- Live mode requires separate credentials, `ALLOW_LIVE_TRADING=true`, and typing
  `LIVE` both when switching modes and when confirming an order.
- Equities and single-leg options use explicit open/close intent. Uncovered option
  writes and equity shorts remain disabled unless separately enabled server-side.
- Open orders can be canceled from Activity; replacement is available through the API.
- Automated tests use provider fakes and never place brokerage orders.

See `backend/README.md` for API details and the paper-account smoke checklist,
`docs/SEC_ACCUMULATION.md` for SEC scoring methodology, and
`frontend/README.md` for frontend commands and the normalized API contract.
