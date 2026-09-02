# Hybrid Stock Prediction Architecture

This document describes StockPulse as it exists today, the hybrid directional
prediction stack being added under `ml/`, and how the two coexist without
replacing each other.

## Current architecture (as-is)

StockPulse is a paper-first trading workstation. Its live API already provides:

| Capability | Location | What it does |
|---|---|---|
| Market OHLCV | `backend/app/services/providers.py` (Alpaca) | On-demand bars for charts and path forecasts |
| Path forecast | `POST /api/v1/forecast` via `KronosService` | Predicted OHLCV path (Kronos or path ensemble) |
| Path ensemble | `forecasting/` | Weighted path adapters (Kronos, Chronos, TimesFM, …) |
| SEC EDGAR | `backend/app/sec/` | 13F / 13D / 13G / Form 4 → Accumulation Score |
| Fundamentals | Finnhub (optional) | Overview metrics merged into quotes |
| Order risk | `backend/app/services/risk.py` | Pre-trade position / ADV / loss gates |
| Portfolio backtest | `kronos_backtest/` | Offline look-ahead-safe portfolio engine |
| LLM research | OpenAI helpers | Narrative over SEC / research queries |

**Important distinction:** today’s “forecast” answers *where the price path may go*.
It does **not** emit a calibrated BUY / HOLD / SELL probability with feature lineage.

Orders remain manual. Forecasts and SEC scores never place trades.

## Proposed hybrid stack

```text
Market + SEC + Fundamentals
            ↓
     Feature engine (ml/features)
            ↓
  Kronos | XGBoost | LightGBM   (plugin models)
            ↓
     Directional ensemble
            ↓
     Probability calibration
            ↓
     Signal risk engine
            ↓
     BUY / HOLD / SELL decision
            ↓
     LLM explanation (numbers from structured payload only)
```

New code lives under top-level `ml/`. The FastAPI layer exposes thin routes that
call into `ml` the same way `KronosService` already imports `forecasting/`.

### Path forecast vs hybrid prediction

| | Path forecast | Hybrid prediction |
|---|---|---|
| Endpoint | `POST /forecast` | `GET /stocks/{ticker}/prediction` |
| Output | Future close path + path segments | Probability, risk, signal |
| Models | Kronos / path ensemble | XGBoost (+ later LightGBM, Kronos adapter) |
| UI | Chart overlay | Decision panel signal |

Both remain available. Hybrid prediction does not replace the chart path.

## Reuse map

- **Alpaca bars** → technical features and training labels
- **SEC pipeline** → institutional / insider flow features (MVP-3); reuse point-in-time rules from `sec/backtest`
- **Finnhub** → fundamental features (MVP-4)
- **Kronos weights** → directional adapter that derives P(up) from path (MVP-2)
- **`forecasting/` path ensemble** → stays for chart mode; directional ensemble is separate under `ml/ensemble`
- **Order `risk.py`** → unchanged; signal risk is `ml/risk` (MVP-5)
- **OpenAI client** → explanation only (MVP-7); never invents numbers

## Canonical entities

Every prediction must be traceable to:

- ticker
- timestamp
- feature snapshot (`feature_version`, `data_cutoff`)
- model version(s) and training data cutoff
- prediction horizon
- probability (raw and calibrated when available)
- risk score
- final signal

Entities (dataclasses / optional SQLite rows): `Security`, `MarketBar`,
`TechnicalFeature` / feature snapshot, `SecInstitutionalFlow`, `SecInsiderFlow`,
`FundamentalFeature`, `ModelPrediction`, `RiskAssessment`, `TradingSignal`,
`PredictionExplanation`.

## Leakage rules (highest-priority correctness)

A prediction for timestamp `T` may only use information publicly available at `T`:

- OHLCV bars with `timestamp <= T`
- SEC filings with acceptance/publication time `<= T`
- Fundamentals as-of `<= T` (no restated future values)

Walk-forward validation must keep train periods strictly before validate/test.
Unit tests assert that feature computation at `T` ignores later bars/filings.

## MVP sequence

1. **MVP-1 (current):** Market → technical features → XGBoost → probability → BUY/HOLD/SELL + API
2. **MVP-2:** Kronos directional adapter, LightGBM, ensemble, calibration
3. **MVP-3:** SEC flow features (PIT-safe)
4. **MVP-4:** Fundamental features
5. **MVP-5:** Independent signal risk engine
6. **MVP-6:** Walk-forward, ablation, SHAP, registry metrics
7. **MVP-7:** LLM explanation from structured results only

## Non-goals

- Auto-trading from signals
- LLM-manufactured predictions or invented metrics
- Treating RSI / Bollinger / MACD crossovers as standalone BUY/SELL rules
- Replacing `POST /forecast` path semantics
- Claiming feature/model superiority without backtest evidence

## Configuration

All weights, horizons, decision thresholds, feature toggles, and provider flags
live in `ml/config/prediction.yaml` (plus env toggles on the API). Models are
plugins: disable any member without redesigning the pipeline.

## Related docs

- [DEVELOPMENT.md](./DEVELOPMENT.md) — local setup, path forecast vs prediction
- [SEC_ACCUMULATION.md](./SEC_ACCUMULATION.md) — EDGAR pipeline
- [BACKTEST.md](./BACKTEST.md) — portfolio backtester (`kronos_backtest/`)
- Feature / model / API docs under `docs/` grow with each MVP
