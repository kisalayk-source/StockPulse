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

## Lineage requirements

Every prediction must include ticker, timestamp, feature snapshot id/version,
model version(s), training data cutoff, horizon, probability, risk score, and
final signal. Predictions without timestamps or cutoff metadata are rejected.

See also [stock-prediction-architecture.md](./stock-prediction-architecture.md).
