"""Decision engine: probability + configurable thresholds → signal."""

from __future__ import annotations

from typing import Any


SIGNAL_BUY = "BUY"
SIGNAL_STRONG_BUY = "STRONG BUY"
SIGNAL_HOLD = "HOLD"
SIGNAL_SELL = "SELL"
SIGNAL_STRONG_SELL = "STRONG SELL"


def decide_signal(
    probability: float,
    *,
    config: dict[str, Any] | None = None,
    model_agreement: float | None = None,
) -> dict[str, Any]:
    """Map calibrated probability to BUY/HOLD/SELL (and strong variants)."""
    decision = {
        "buy_probability": 0.65,
        "strong_buy_probability": 0.80,
        "sell_probability": 0.35,
        "strong_sell_probability": 0.20,
        "minimum_model_agreement": 0.60,
    }
    if config:
        decision.update(config)

    p = float(probability)
    if not 0.0 <= p <= 1.0:
        raise ValueError("probability must be in [0, 1]")

    agreement_ok = True
    if model_agreement is not None:
        agreement_ok = float(model_agreement) >= float(decision["minimum_model_agreement"])

    if p >= float(decision["strong_buy_probability"]) and agreement_ok:
        signal = SIGNAL_STRONG_BUY
    elif p >= float(decision["buy_probability"]) and agreement_ok:
        signal = SIGNAL_BUY
    elif p <= float(decision["strong_sell_probability"]) and agreement_ok:
        signal = SIGNAL_STRONG_SELL
    elif p <= float(decision["sell_probability"]) and agreement_ok:
        signal = SIGNAL_SELL
    else:
        signal = SIGNAL_HOLD

    return {
        "signal": signal,
        "probability": p,
        "model_agreement": model_agreement,
        "thresholds": {
            "buy_probability": float(decision["buy_probability"]),
            "strong_buy_probability": float(decision["strong_buy_probability"]),
            "sell_probability": float(decision["sell_probability"]),
            "strong_sell_probability": float(decision["strong_sell_probability"]),
            "minimum_model_agreement": float(decision["minimum_model_agreement"]),
        },
    }
