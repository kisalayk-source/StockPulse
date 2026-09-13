# Signal risk engine

`ml/risk/risk_engine.py` estimates signal-level risk and can veto or downgrade
BUY-side signals. This is **independent** from order pre-trade gates in
`backend/app/services/risk.py` and trading-agent portfolio limits.

Plain-language overview: [mvp-roadmap.md](./mvp-roadmap.md#mvp-5--signal-risk-safety-net).

## MVP-5 (implemented)

`assess_risk(...)` blends:

- Rolling volatility (and ATR% when price is available)
- Absolute drawdown
- Optional **position concentration** (fraction of equity; 0 when unknown)
- Model disagreement and probability edge
- Mild regime penalty for BEAR / HIGH_VOL / SIDEWAYS

`apply_risk_gate(signal, risk, ...)` then:

| Condition | BUY / STRONG BUY effect |
|---|---|
| Risk disabled | Unchanged |
| Hard breach: `volatility > max_volatility`, `\|drawdown\| > max_drawdown`, or `concentration > max_position_concentration` | → HOLD (veto) |
| `risk_score >= veto_risk_score` | → HOLD (veto) |
| `risk_score >= downgrade_risk_score` | STRONG BUY → BUY; BUY → HOLD |
| Sell / HOLD | Never upgraded or flipped |

Config lives under `risk:` in `ml/config/prediction.yaml` (`enabled: true` by default).
`PredictionEngine` applies the gate after `decide_signal` and records
`decision.risk_gate` / `risk.gate` with action and reasons.

Callers may pass `position_concentration` into `predict_from_bars` when book
context is known; without it, concentration only affects the score when supplied.
