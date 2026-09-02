# Model engine

Directional models implement `ml.models.base.ForecastModel`:

```python
train(dataset) -> None
predict(features) -> labels
predict_probability(features) -> float
```

This is separate from `forecasting.core.base.ForecastModel` (path adapters).

## MVP-1

- `XGBoostModel` — binary classifier on technical features for horizons `1d`/`5d`/`20d`
- Target: forward return ≥ `return_threshold` (config; default `0.0`)
- Artifacts cached in `backend/data/model_registry/`

## Scaffolded

- `LightGBMModel` — MVP-2
- `KronosModel` directional adapter — MVP-2
- Ensemble strategies in `ml/ensemble/` — MVP-2
- Calibration hooks in `ml/calibration/` — identity passthrough until MVP-2

Config: `ml/config/prediction.yaml`.
