"""Signal risk engine (MVP-5). Independent from order pre-trade gates."""

from __future__ import annotations

from typing import Any

from ml.decision.engine import SIGNAL_BUY, SIGNAL_HOLD, SIGNAL_STRONG_BUY

_BUY_SIDE = {SIGNAL_BUY, SIGNAL_STRONG_BUY}

_DEFAULT_WEIGHTS = {
    "volatility": 0.30,
    "drawdown": 0.25,
    "concentration": 0.20,
    "disagreement": 0.15,
    "edge": 0.10,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def assess_risk(
    *,
    predicted_probability: float,
    expected_return: float | None = None,
    volatility: float | None = None,
    atr: float | None = None,
    price: float | None = None,
    drawdown: float | None = None,
    market_regime: str | None = None,
    model_agreement: float | None = None,
    data_quality: float = 1.0,
    position_concentration: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score signal-level risk from vol, drawdown, concentration, and agreement.

    Does not change the trading signal by itself — use :func:`apply_risk_gate`.
    """
    cfg = dict(config or {})
    weights = {**_DEFAULT_WEIGHTS, **(cfg.get("weights") or {})}

    disagreement = 1.0 - float(model_agreement if model_agreement is not None else 1.0)
    vol_component = _clamp01(float(volatility or 0.0) * 10.0)
    if atr is not None and price is not None and float(price) > 0:
        atr_pct = float(atr) / float(price)
        vol_component = max(vol_component, _clamp01(atr_pct * 8.0))

    dd_component = _clamp01(abs(float(drawdown or 0.0)))
    concentration = float(position_concentration) if position_concentration is not None else 0.0
    concentration_component = _clamp01(concentration)

    edge_certainty = abs(float(predicted_probability) - 0.5) * 2.0
    edge_component = _clamp01(1.0 - edge_certainty)

    regime = (market_regime or "").upper()
    regime_penalty = 0.0
    if regime in {"BEAR", "HIGH_VOL", "CRISIS"}:
        regime_penalty = float(cfg.get("regime_penalty", 0.10))
    elif regime in {"SIDEWAYS", "RANGE"}:
        regime_penalty = float(cfg.get("regime_penalty_mild", 0.05))

    w_vol = float(weights.get("volatility", 0.30))
    w_dd = float(weights.get("drawdown", 0.25))
    w_conc = float(weights.get("concentration", 0.20))
    w_dis = float(weights.get("disagreement", 0.15))
    w_edge = float(weights.get("edge", 0.10))
    weight_sum = w_vol + w_dd + w_conc + w_dis + w_edge
    if weight_sum <= 0:
        weight_sum = 1.0

    blended = (
        w_vol * vol_component
        + w_dd * dd_component
        + w_conc * concentration_component
        + w_dis * disagreement
        + w_edge * edge_component
    ) / weight_sum
    risk_score = _clamp01(blended + regime_penalty)

    confidence = _clamp01(float(data_quality) * (1.0 - 0.5 * disagreement) * edge_certainty)

    reasons: list[str] = []
    if vol_component >= 0.7:
        reasons.append("elevated volatility")
    if dd_component >= 0.7:
        reasons.append("deep drawdown")
    if concentration_component >= 0.7:
        reasons.append("high position concentration")
    if disagreement >= 0.5:
        reasons.append("model disagreement")
    if regime_penalty > 0:
        reasons.append(f"adverse regime ({regime or 'unknown'})")

    return {
        "risk_score": round(risk_score, 4),
        "confidence_score": round(confidence, 4),
        "expected_return": expected_return,
        "max_loss_estimate": abs(float(drawdown)) if drawdown is not None else None,
        "components": {
            "volatility": round(vol_component, 4),
            "drawdown": round(dd_component, 4),
            "concentration": round(concentration_component, 4),
            "disagreement": round(disagreement, 4),
            "edge": round(edge_component, 4),
            "regime_penalty": round(regime_penalty, 4),
            "data_quality": float(data_quality),
        },
        "reasons": reasons,
        "enabled": bool(cfg.get("enabled", False)),
    }


def apply_risk_gate(
    signal: str,
    risk: dict[str, Any],
    *,
    volatility: float | None = None,
    drawdown: float | None = None,
    position_concentration: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Veto or downgrade BUY-side signals when risk thresholds are breached.

    Sell-side signals are left unchanged. When risk is disabled, returns the
    original signal with ``action='none'``.
    """
    cfg = dict(config or {})
    original = signal
    if not bool(cfg.get("enabled", False)):
        return {
            "signal": original,
            "original_signal": original,
            "action": "none",
            "reasons": [],
            "gated": False,
        }

    if original not in _BUY_SIDE:
        return {
            "signal": original,
            "original_signal": original,
            "action": "none",
            "reasons": [],
            "gated": False,
        }

    risk_score = float(risk.get("risk_score") or 0.0)
    max_risk = float(cfg.get("max_risk_score", 0.70))
    veto_risk = float(cfg.get("veto_risk_score", max(max_risk, 0.85)))
    downgrade_risk = float(cfg.get("downgrade_risk_score", max_risk))

    max_vol = cfg.get("max_volatility")
    max_dd = cfg.get("max_drawdown")
    max_conc = cfg.get("max_position_concentration")

    reasons: list[str] = list(risk.get("reasons") or [])
    hard_veto = False

    if max_vol is not None and volatility is not None and float(volatility) > float(max_vol):
        hard_veto = True
        reasons.append(f"volatility {float(volatility):.4f} > max_volatility {float(max_vol)}")
    if max_dd is not None and drawdown is not None and abs(float(drawdown)) > float(max_dd):
        hard_veto = True
        reasons.append(f"drawdown {abs(float(drawdown)):.4f} > max_drawdown {float(max_dd)}")
    if (
        max_conc is not None
        and position_concentration is not None
        and float(position_concentration) > float(max_conc)
    ):
        hard_veto = True
        reasons.append(
            f"concentration {float(position_concentration):.4f} > max_position_concentration {float(max_conc)}"
        )

    if hard_veto or risk_score >= veto_risk:
        return {
            "signal": SIGNAL_HOLD,
            "original_signal": original,
            "action": "veto",
            "reasons": reasons or [f"risk_score {risk_score:.4f} >= veto_risk_score {veto_risk}"],
            "gated": True,
        }

    if risk_score >= downgrade_risk:
        if original == SIGNAL_STRONG_BUY:
            return {
                "signal": SIGNAL_BUY,
                "original_signal": original,
                "action": "downgrade",
                "reasons": reasons or [f"risk_score {risk_score:.4f} >= downgrade_risk_score {downgrade_risk}"],
                "gated": True,
            }
        return {
            "signal": SIGNAL_HOLD,
            "original_signal": original,
            "action": "veto",
            "reasons": reasons or [f"risk_score {risk_score:.4f} >= downgrade_risk_score {downgrade_risk}"],
            "gated": True,
        }

    return {
        "signal": original,
        "original_signal": original,
        "action": "none",
        "reasons": [],
        "gated": False,
    }


__all__ = ["assess_risk", "apply_risk_gate"]
