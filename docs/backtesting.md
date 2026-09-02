# Prediction backtesting

Walk-forward backtesting, ablation, and SHAP analysis for the hybrid engine land
in MVP-6 under `ml/backtesting/`.

Until then, reuse:

- Path / portfolio backtests: [BACKTEST.md](./BACKTEST.md) (`kronos_backtest/`)
- SEC point-in-time score backtests: `backend/app/sec/backtest/`

Rules already enforced in MVP-1 unit tests:

- Feature snapshots at timestamp `T` ignore bars after `T`
- Training labels never use forward returns beyond available history
