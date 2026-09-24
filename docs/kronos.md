# Kronos in hybrid prediction

Plain-language MVP overview: [mvp-roadmap.md](./mvp-roadmap.md).

## Path forecast (existing)

`POST /api/v1/forecast` uses `KronosService` and optional `forecasting/` ensemble to
produce an OHLCV **path** for charting. This path never places orders by itself.
The path ensemble runs persistence, Kronos small, Chronos (`amazon/chronos-t5-small`), and TimesFM (`google/timesfm-3.0-pytorch`). Lag-Llama stays off until its package is installed.

For the trading agent, the path is used for **sizing and targets only**; BUY/SELL
comes from calibrated hybrid prediction (see agent alignment in
[mvp-roadmap.md](./mvp-roadmap.md#agent-alignment-done) and
[trading-agent.md](./trading-agent.md)).

## Directional adapter (MVP-2 — implemented)

`ml.models.kronos.KronosModel` maps path outcomes into a directional probability
through the shared `ForecastModel` plugin interface:

- Inputs: path payload `trend.forecast_change` / `net_forecast_change`, optional volatility
- Mapping: sigmoid(`change / (vol * sqrt(horizon bars))`) → P(up) in `(0, 1)` — no RSI/MACD rules. One-day volatility is stretched by the horizon so a multi-day move is not treated as a one-day shock. This probability is not Platt-fit on its own; trees stay calibrated and the ensemble blend is the final P(up).
- Wired via `PredictionService` → `path_forecast_fn` calling `KronosService.forecast`
  (`evaluate=False`, small context; `path_engine` from YAML)

Enable or disable via `models.kronos.enabled` in `ml/config/prediction.yaml`.
Chart path semantics are unchanged.

Technical indicators are computed externally and are not assumed to be internal
to Kronos.
