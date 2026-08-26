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
`docs/StockPulse-Finance-Glossary.pdf`.

## Multi-model forecasting (research)

Standalone package under `forecasting/`. StockPulse chart **Forecast** mode wires the
same ensemble through `POST /api/v1/forecast` with `engine=ensemble` (no separate
server). **Kronos** mode (`engine=kronos`) keeps the single Kronos model path.
Sampling defaults (`KRONOS_TEMPERATURE=0.6`, `KRONOS_SAMPLE_COUNT=5`,
`KRONOS_TOP_P=0.9` in `backend/.env.example`) apply to both paths for smoother
chart trajectories.
The optional research API on `:8001` remains for offline/eval tooling only.
Enable/disable models in `forecasting/config/models.yaml`.

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
