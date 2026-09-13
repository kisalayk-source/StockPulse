# Prediction backtesting

Walk-forward backtesting, ablation, and SHAP for the hybrid directional engine
live under `ml/backtesting/` (MVP-6).

## Capabilities

| API | Role |
|---|---|
| `walk_forward_splits` | Expanding/rolling folds with embargo (≥ label horizon) |
| `run_backtest` | Train XGB/LGBM per fold on technical features; OOS metrics + SHAP |
| `run_ablation` | Drop feature groups (`momentum`, `volatility`, …) and compare accuracy |
| `classification_metrics` | Accuracy, hit-rate, AUC, Brier, log-loss |
| `compare_to_benchmarks` | Buy-and-hold return + always-long baseline |
| `explain_tree_model` | SHAP TreeExplainer when `shap` is installed; else feature importances |

Reuse the same adapters and label construction as live prediction
(`compute_technical_frame`, `add_forward_return_target`, `XGBoostModel` /
`LightGBMModel`). No parallel training stack.

## Leakage rules

- Train indices always end strictly before test indices
- `embargo_bars` defaults to `horizon_bars` so forward-return labels cannot
  overlap the test window
- Feature snapshots at `T` still ignore bars after `T` (MVP-1 unit tests)

## Registry metrics

On live retrain, `PredictionEngine` writes holdout `validation_metrics`
(accuracy, AUC, Brier, log-loss, …) onto each `ModelRecord` in
`backend/data/model_registry/`.

## Related

- Portfolio / path backtests: [BACKTEST.md](./BACKTEST.md) (`kronos_backtest/`)
- SEC PIT score backtests: `backend/app/sec/backtest/`
- Evaluation policy: [model-evaluation.md](./model-evaluation.md)
