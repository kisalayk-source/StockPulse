# Hybrid prediction data model

Canonical entities used by the directional prediction engine (`ml/`).

## Entities

| Entity | Purpose |
|---|---|
| `Security` | Ticker identity metadata |
| `MarketBar` | OHLCV observation |
| `FeatureSnapshot` | Immutable feature vector at `data_cutoff` |
| `ModelPrediction` | Per-model probability with training cutoff |
| `RiskAssessment` | Signal-level risk (not order gates) |
| `TradingSignal` | BUY / HOLD / SELL decision |
| `PredictionExplanation` | Template/LLM text bound to structured numbers |

## Trading agent persistence (SQLite)

| Entity / table | Purpose |
|---|---|
| `AgentConfig` (`agent_configs`) | Per-user agent settings; `universe` JSON is the **saved** risk portfolio (max 50) for auto-cycles |
| `AgentRun` | Cycle runs; `summary.universe_scan` records last-cycle symbols (ad-hoc or saved) |
| `TradeCandidate` / `TradePlan` / `AgentOrder` / `AgentPosition` / `AgentEvent` | Cycle artifacts and book |

Ad-hoc cycle `symbols` are **not** written to `AgentConfig.universe`. See [trading-agent.md](./trading-agent.md).

## Lineage requirements

Every prediction must include ticker, timestamp, feature snapshot id/version,
model version(s), training data cutoff, horizon, probability, risk score, and
final signal. Predictions without timestamps or cutoff metadata are rejected.

See also [mvp-roadmap.md](./mvp-roadmap.md) (plain language) and
[stock-prediction-architecture.md](./stock-prediction-architecture.md).
