# Model evaluation

Objective comparison of Kronos / XGBoost / LightGBM / hybrid ensembles requires
the walk-forward + ablation harness (MVP-6).

Until then:

- Do not claim a feature group or model is “better” without shared periods
- Use identical cutoffs and leakage rules across experiments
- Track registry metrics on each saved artifact (`ml/registry`)

Related: [backtesting.md](./backtesting.md), [model-engine.md](./model-engine.md).
