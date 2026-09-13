# Kronos in hybrid prediction

Plain-language MVP overview: [mvp-roadmap.md](./mvp-roadmap.md).

## Path forecast (existing)

`POST /api/v1/forecast` uses `KronosService` and optional `forecasting/` ensemble to
produce an OHLCV **path** for charting. This path never places orders by itself.

For the trading agent, the path is used for **sizing and targets only**; BUY/SELL
comes from calibrated hybrid prediction (see agent alignment in
[mvp-roadmap.md](./mvp-roadmap.md#agent-alignment-done)).

## Directional adapter (MVP-2 — implemented)

`ml.models.kronos.KronosModel` maps path outcomes into a directional probability
through the shared `ForecastModel` plugin interface:

- Inputs: path payload `trend.forecast_change` / `net_forecast_change`, optional volatility
- Mapping: sigmoid(`change / vol`) → P(up) in `(0, 1)` — no RSI/MACD rules
- Wired via `PredictionService` → `path_forecast_fn` calling `KronosService.forecast`
  (`evaluate=False`, small context; `path_engine` from YAML)

Enable or disable via `models.kronos.enabled` in `ml/config/prediction.yaml`.
Chart path semantics are unchanged.

Technical indicators are computed externally and are not assumed to be internal
to Kronos.
