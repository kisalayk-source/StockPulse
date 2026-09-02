# Development

## Prerequisites

- Git
- Python 3.10–3.12 (3.12 is used in application CI)
- Node.js 22 and npm
- Docker with Compose v2 (optional)

Use separate virtual environments when working on the core model and StockPulse
backend because their dependency sets serve different use cases.

## Core model

From the repository root:

```bash
python -m venv .venv
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` keeps numerically sensitive packages pinned and gives
NumPy/Torch bounded ranges for platform wheel compatibility. Propose dependency
updates in isolated pull requests and run the model regression workflow before
merging. The regression suite downloads pinned Hugging Face revisions and is
not part of pull-request CI:

```bash
pytest -q tests/test_kronos_regression.py
```

## Documentation PDFs

```powershell
# Product/ops guide
powershell -ExecutionPolicy Bypass -File scripts/build-docs-pdf.ps1

# Technical architecture + finance glossary
powershell -ExecutionPolicy Bypass -File scripts/build-guide-pdfs.ps1
```

Outputs: `docs/StockPulse.pdf`, `docs/StockPulse-Architecture.pdf`,
`docs/StockPulse-Finance-Glossary.pdf`. See also `docs/SEC_ACCUMULATION.md`.

## Multi-model forecasting (research)

Standalone package under `forecasting/`. StockPulse chart **Forecast** mode wires the
same ensemble through `POST /api/v1/forecast` with `engine=ensemble` (no separate
server). **Kronos** mode (`engine=kronos`) keeps the single Kronos model path.
Sampling defaults (`KRONOS_TEMPERATURE=0.6`, `KRONOS_SAMPLE_COUNT=5`,
`KRONOS_TOP_P=0.9` in `backend/.env.example`) apply to both paths for smoother
chart trajectories.
The optional research API on `:8001` remains for offline/eval tooling only.
Enable/disable models in `forecasting/config/models.yaml`.

**Path forecast vs hybrid prediction:** `POST /forecast` returns an OHLCV path for
the chart. Hybrid directional signals live under `ml/` and
`GET /api/v1/stocks/{ticker}/prediction` (technical features → XGBoost in MVP-1).
See [stock-prediction-architecture.md](./stock-prediction-architecture.md).

```bash
# from repo root, with the core-model venv
pip install -r forecasting/requirements.txt
pytest -q forecasting/tests

# optional model extras (prefer isolated envs if pins conflict)
pip install -r forecasting/requirements-chronos.txt
pip install -r forecasting/requirements-timesfm.txt

# research API (does not replace StockPulse :8000; UI does not use this port)
uvicorn forecasting.api.serve:app --host 127.0.0.1 --port 8001
```

## Production backtester

The look-ahead-safe engine lives in `kronos_backtest/` and is documented in
[BACKTEST.md](./BACKTEST.md). It does not download model weights:

```bash
pytest -q tests/backtest
python -m kronos_backtest --config configs/backtest.yaml --predictor dummy
```

## StockPulse backend

```bash
python -m venv .venv-backend
pip install -r backend/requirements.txt
cd backend
pytest -q
uvicorn app.main:app --reload
```

Copy `backend/.env.example` to `backend/.env` only for local use. Tests use
fakes; do not put real credentials in fixtures or commits.

### Hybrid directional prediction (MVP-1)

- Code: `ml/` (features, XGBoost adapter, decision engine, registry)
- Config: `ml/config/prediction.yaml`
- API: `GET /api/v1/stocks/{ticker}/prediction` (also `/features`, `/signals`, `/risk`, `/explanation`)
- Docs: [stock-prediction-architecture.md](./stock-prediction-architecture.md), [api.md](./api.md)

```bash
# from repo root
pytest -q ml/tests
cd backend
pytest -q tests/test_prediction_api.py
```

### SEC accumulation

- Code: `backend/app/sec/`
- Config: `backend/configs/sec_accumulation.yaml`, env vars in `backend/.env.example`
- Docs: [SEC_ACCUMULATION.md](./SEC_ACCUMULATION.md)

```bash
cd backend
pytest -q tests/test_sec_*.py tests/test_research_query.py
python scripts/sec_backtest.py XOM --days 365
```

To trigger a scan manually (requires running API with credentials):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/accumulation/scan -H "Authorization: Bearer …"
curl http://127.0.0.1:8000/api/v1/accumulation/scan/status -H "Authorization: Bearer …"
```

## StockPulse frontend

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
npm run dev
```

## LAN publish (local network)

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/publish-kronos-lan.ps1
```

The script builds the frontend, starts the API on loopback `:8000`, **waits for `/api/v1/health`**, then starts Vite preview on `0.0.0.0:5173`. LAN clients use the UI proxy — the API is not exposed off loopback. Logs: `runtime-logs/backend.*.log`, `runtime-logs/frontend.*.log`. A watchdog (`scripts/watch-kronos-lan.ps1`) can restart the stack when health checks fail.

If you see **502** on API routes through the UI, confirm `http://127.0.0.1:8000/api/v1/health` responds and republish.

## Containers

Build and start the StockPulse API and frontend from the repository root:

```bash
docker compose up --build
```

Open the frontend at `http://localhost:5173` and API documentation at
`http://localhost:8000/docs`. The optional legacy web UI is available with:

```bash
docker compose --profile legacy up --build webui
```

It listens on `http://localhost:7070`. Model downloads are cached in the named
`huggingface-cache` volume. Keep live trading disabled and provide credentials
through your local environment or an untracked env file.

## Generated artifacts

Runtime logs, downloaded weights, predictions, and generated reports should not
be committed. Some historical prediction outputs are already tracked; they have
not been deleted to avoid removing potentially intentional project artifacts.
Maintainers should review them separately and, if appropriate, remove them in a
dedicated, clearly explained pull request.

## PDF manual

```powershell
pip install fpdf2
powershell -ExecutionPolicy Bypass -File scripts/build-docs-pdf.ps1
```

Output: `docs/StockPulse.pdf`. Print-ready HTML: `docs/StockPulse.html`.
SEC accumulation reference: `docs/SEC_ACCUMULATION.md`.
