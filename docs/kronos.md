# Kronos in hybrid prediction

## Path forecast (existing)

`POST /api/v1/forecast` uses `KronosService` and optional `forecasting/` ensemble to
produce an OHLCV **path** for charting. This path never places orders.

## Directional adapter (MVP-2)

`ml.models.kronos.KronosModel` will map path outcomes into a directional
probability through the shared `ForecastModel` plugin interface. Kronos remains
interchangeable: it can be disabled in `ml/config/prediction.yaml` without
changing the decision pipeline.

Technical indicators are computed externally and are not assumed to be internal
to Kronos.
