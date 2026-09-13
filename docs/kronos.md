# Kronos in hybrid prediction

## Path forecast (existing)

`POST /api/v1/forecast` uses `KronosService` and optional `forecasting/` ensemble to
produce an OHLCV **path** for charting. This path never places orders.

## Directional adapter (MVP-2 — implemented)

`ml.models.kronos.KronosModel` maps path outcomes into a directional probability
through the shared `ForecastModel` plugin interface:

- Inputs: path payload `trend.forecast_change` / `net_forecast_change`, optional volatility
- Mapping: sigmoid(`change / vol`) → P(up) in `(0, 1)` — no RSI/MACD rules
- Wired via `PredictionService` → `path_forecast_fn` calling `KronosService.forecast`
  (`evaluate=False`, small context; `path_engine` from YAML)

Kronos remains interchangeable: keep `models.kronos.enabled: false` (default) without
changing the decision pipeline. Chart path semantics are unchanged.

Technical indicators are computed externally and are not assumed to be internal
to Kronos.
