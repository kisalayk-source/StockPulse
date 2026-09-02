# Signal risk engine

`ml/risk/risk_engine.py` estimates signal-level risk and confidence from
probability, volatility, drawdown, regime, and model agreement.

This is **independent** from order pre-trade gates in
`backend/app/services/risk.py`.

MVP-1 ships a provisional scorer; methodology hardens in MVP-5.
Decision thresholds remain configurable and separate from risk scoring.
