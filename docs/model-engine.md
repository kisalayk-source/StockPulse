# Model engine

Directional models implement `ml.models.base.ForecastModel`:

```python
train(dataset) -> None
predict(features) -> labels
predict_probability(features) -> float
```

This is separate from `forecasting.core.base.ForecastModel` (path adapters).

Plain-language MVP overview: [mvp-roadmap.md](./mvp-roadmap.md).

## MVP-1 (implemented)

- `XGBoostModel` — binary classifier on technical features for horizons `1d`/`5d`/`20d`
- Target: forward return ≥ `return_threshold` (config; default `0.0`)
- Artifacts cached in `backend/data/model_registry/`

## MVP-2 (implemented)

- `LightGBMModel` — same feature/target interface as XGBoost
- `KronosModel` directional adapter — maps path `forecast_change` → P(up) via sigmoid
- Weighted ensemble (`equal_weight` / `performance_weighted`) over enabled members
- Calibration: `identity` | `platt` | `isotonic` fitted on chronological holdout and stored with tree artifacts
- Enable members and weights in `ml/config/prediction.yaml`
- Prefer `ensemble.strategy: performance_weighted` when running the full trio

Config: `ml/config/prediction.yaml`.
