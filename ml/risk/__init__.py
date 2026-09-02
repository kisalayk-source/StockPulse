"""Signal risk engine scaffold (MVP-5). Independent from order risk gates."""

from __future__ import annotations

from typing import Any


def assess_risk(
    *,
    predicted_probability: float,
    expected_return: float | None = None,
    volatility: float | None = None,
    atr: float | None = None,
    drawdown: float | None = None,
    market_regime: str | None = None,
    model_agreement: float | None = None,
    data_quality: float = 1.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce a provisional risk score until MVP-5 fleshes out methodology."""
    _ = config, atr, market_regime
    disagreement = 1.0 - float(model_agreement if model_agreement is not None else 1.0)
    vol_component = min(1.0, float(volatility or 0.0) * 10.0)
    dd_component = min(1.0, abs(float(drawdown or 0.0)))
    edge_uncertainty = abs(float(predicted_probability) - 0.5) * 2.0
    risk_score = min(
        1.0,
        0.35 * vol_component + 0.25 * dd_component + 0.25 * disagreement + 0.15 * (1.0 - edge_uncertainty),
    )
    confidence = max(0.0, min(1.0, float(data_quality) * (1.0 - 0.5 * disagreement) * edge_uncertainty))
    return {
        "risk_score": round(risk_score, 4),
        "confidence_score": round(confidence, 4),
        "expected_return": expected_return,
        "max_loss_estimate": abs(float(drawdown)) if drawdown is not None else None,
        "components": {
            "volatility": vol_component,
            "drawdown": dd_component,
            "disagreement": disagreement,
            "data_quality": float(data_quality),
        },
    }
