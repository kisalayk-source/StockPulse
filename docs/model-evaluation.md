# Model evaluation

Objective comparison of Kronos / XGBoost / LightGBM / hybrid ensembles uses the
walk-forward + ablation harness under `ml/backtesting/` (MVP-6).

## Rules

- Do not claim a feature group or model is “better” without shared periods
- Use identical cutoffs and leakage rules across experiments
- Track registry metrics on each saved artifact (`ml/registry`)

## Harness

```python
from ml.backtesting import run_backtest, run_ablation

report = run_backtest(ohlcv, model_type="xgboost", horizon_bars=5)
ablation = run_ablation(ohlcv, groups=["momentum", "volatility"])
```

Reports include per-fold metrics, overall accuracy/AUC/Brier, benchmarks, and a
SHAP (or importance) summary from the last fold’s model.

Config defaults: `evaluation:` in `ml/config/prediction.yaml`.

Related: [backtesting.md](./backtesting.md), [model-engine.md](./model-engine.md).
