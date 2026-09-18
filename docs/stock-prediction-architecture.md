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
| Government contracts | `backend/app/government/` | SAM.gov + USAspending → government / early-signal scores |
| Fundamentals | Finnhub (optional) | Overview metrics merged into quotes |
| Order risk | `backend/app/services/risk.py` | Pre-trade position / ADV / loss gates |
| Portfolio backtest | `kronos_backtest/` | Offline look-ahead-safe portfolio engine |
| LLM research | OpenAI helpers | Narrative over SEC / research queries |

**Important distinction:** today’s “forecast” answers *where the price path may go*.
It does **not** emit a calibrated BUY / HOLD / SELL probability with feature lineage.

Orders remain manual. Forecasts, SEC scores, and government scores never place trades.

## Proposed hybrid stack

```text
Market + SEC + Fundamentals + Government
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
- **Government pipeline** → award / obligation / opportunity features; PIT filter `event_at` + `published_at` ≤ `as_of`
- **Finnhub** → fundamental features (MVP-4); optional revenue proxy for government materiality
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
`TechnicalFeature` / feature snapshot (`technical` / `sec` / `fundamentals` /
`government`), `SecInstitutionalFlow`, `SecInsiderFlow`, `FundamentalFeature`,
`GovernmentEvent` / `GovernmentContract` / `GovernmentCompanyMapping`,
`ModelPrediction`, `RiskAssessment`, `TradingSignal`, `PredictionExplanation`.

## Leakage rules (highest-priority correctness)

A prediction for timestamp `T` may only use information publicly available at `T`:

- OHLCV bars with `timestamp <= T`
- SEC filings with acceptance/publication time `<= T`
- Government events with `event_at <= T` and `published_at <= T` (when present)
- Fundamentals as-of `<= T` (no restated future values)

Walk-forward validation must keep train periods strictly before validate/test.
Unit tests assert that feature computation at `T` ignores later bars/filings/events.

## MVP sequence

Plain-language overview for non-engineers: **[mvp-roadmap.md](./mvp-roadmap.md)**.

1. **MVP-1 (done):** Market → technical features → XGBoost → probability → BUY/HOLD/SELL + API
2. **MVP-2 (done):** Kronos directional adapter, LightGBM, weighted ensemble, Platt/isotonic calibration
3. **MVP-3 (done):** SEC flow features (PIT-safe) into `FeatureSnapshot.sec`
4. **MVP-4 (done):** Fundamental features from Finnhub into `FeatureSnapshot.fundamentals`
5. **MVP-5 (done):** Independent signal risk engine (veto/downgrade BUY on vol, drawdown, concentration)
6. **MVP-6 (done):** Walk-forward, ablation, SHAP, registry metrics
7. **MVP-7 (done):** LLM explanation from structured results only (template always; OpenAI optional + grounded)

**Government contracts (done):** SAM.gov + USAspending → `FeatureSnapshot.government`
(`feature_version` `1.1.0`); Market `GovernmentPanel` + API — see
[government.md](./government.md).

**Agent alignment (done):** hybrid owns BUY/SELL; Kronos path owns sizing/targets only — see [mvp-roadmap.md](./mvp-roadmap.md#agent-alignment-done) and the section below.

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

## Agent alignment

Once the calibrated hybrid ensemble is live, the autonomous trading agent uses:

| Source | Role |
|---|---|
| Hybrid prediction (`PredictionService`) | **Only** BUY / HOLD / SELL (and strong variants) |
| Kronos / path ensemble | Expected move, target/stop hints, and position sizing — **not** a rival signal |

If hybrid is unavailable, the agent emits `HOLD` (`signal_source=unavailable`)
rather than inventing direction from the path. Setting:
`agent_require_hybrid_signal` (default `true`).

**Universe:** scheduled auto-cycles use the saved risk portfolio (`config.universe`,
max 50). Manual cycles may pass any valid ticker list via `POST /trading-agent/cycle`
`symbols` without adding them to that list — see [trading-agent.md](./trading-agent.md).

## Related docs

- [mvp-roadmap.md](./mvp-roadmap.md) — plain-language MVP-1…7 + agent alignment + government
- [trading-agent.md](./trading-agent.md) — agent cycles, ad-hoc symbols, API/UI
- [how-forecast-works.md](./how-forecast-works.md) — everyday chart path vs model stance
- [DEVELOPMENT.md](./DEVELOPMENT.md) — local setup, path forecast vs prediction
- [SEC_ACCUMULATION.md](./SEC_ACCUMULATION.md) — EDGAR pipeline
- [government.md](./government.md) — government contract analysis
- [BACKTEST.md](./BACKTEST.md) — portfolio backtester (`kronos_backtest/`)
- Feature / model / risk / eval docs under `docs/` (linked from the MVP roadmap)
