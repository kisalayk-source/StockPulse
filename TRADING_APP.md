# StockPulse

The trading app is split into:

- `backend/`: FastAPI, Alpaca market/trading APIs, Finnhub fundamentals, and Kronos forecasts
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
```

until paper-mode validation is complete. Before intentional network access, set a
strong `API_KEY`, configure the frontend environment, and restrict CORS and firewall
rules. Use `sip` only with an Alpaca SIP data subscription. Secrets remain in
`backend/.env`, which is ignored by Git. The current personal-app live confirmation
flow uses the literal `LIVE`; API authentication and network controls provide the
actual access boundary.

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

## Safety

- Kronos forecasts are display-only and cannot submit orders.
- Every order requires a review dialog.
- Live mode requires separate credentials, `ALLOW_LIVE_TRADING=true`, and typing
  `LIVE` both when switching modes and when confirming an order.
- Equities and single-leg options use explicit open/close intent. Uncovered option
  writes and equity shorts remain disabled unless separately enabled server-side.
- Open orders can be canceled from Activity; replacement is available through the API.
- Automated tests use provider fakes and never place brokerage orders.

See `backend/README.md` for API details and the paper-account smoke checklist, and
`frontend/README.md` for frontend commands and the normalized API contract.
