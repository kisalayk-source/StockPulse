"""Signal risk engine unit tests (MVP-5)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.risk import apply_risk_gate, assess_risk


def _enabled_cfg(**overrides):
    cfg = {
        "enabled": True,
        "max_risk_score": 0.70,
        "downgrade_risk_score": 0.70,
        "veto_risk_score": 0.85,
        "max_volatility": 0.045,
        "max_drawdown": 0.25,
        "max_position_concentration": 0.15,
    }
    cfg.update(overrides)
    return cfg


def test_assess_risk_includes_concentration_and_config_weights() -> None:
    risk = assess_risk(
        predicted_probability=0.7,
        volatility=0.02,
        drawdown=-0.05,
        position_concentration=0.4,
        model_agreement=0.9,
        data_quality=1.0,
        config=_enabled_cfg(),
    )
    assert 0.0 <= risk["risk_score"] <= 1.0
    assert risk["components"]["concentration"] == 0.4
    assert risk["enabled"] is True
    assert "concentration" in risk["components"]


def test_disabled_gate_leaves_buy_unchanged() -> None:
    risk = assess_risk(
        predicted_probability=0.9,
        volatility=0.10,
        drawdown=-0.40,
        position_concentration=0.5,
        config={"enabled": False},
    )
    gate = apply_risk_gate("BUY", risk, volatility=0.10, drawdown=-0.40, position_concentration=0.5, config={"enabled": False})
    assert gate["signal"] == "BUY"
    assert gate["action"] == "none"
    assert gate["gated"] is False


def test_high_volatility_vetoes_buy() -> None:
    cfg = _enabled_cfg()
    risk = assess_risk(
        predicted_probability=0.8,
        volatility=0.06,
        drawdown=-0.05,
        model_agreement=1.0,
        config=cfg,
    )
    gate = apply_risk_gate(
        "BUY",
        risk,
        volatility=0.06,
        drawdown=-0.05,
        config=cfg,
    )
    assert gate["signal"] == "HOLD"
    assert gate["action"] == "veto"
    assert gate["gated"] is True
    assert any("volatility" in r for r in gate["reasons"])


def test_deep_drawdown_vetoes_strong_buy() -> None:
    cfg = _enabled_cfg()
    risk = assess_risk(
        predicted_probability=0.9,
        volatility=0.01,
        drawdown=-0.35,
        model_agreement=1.0,
        config=cfg,
    )
    gate = apply_risk_gate("STRONG BUY", risk, volatility=0.01, drawdown=-0.35, config=cfg)
    assert gate["signal"] == "HOLD"
    assert gate["action"] == "veto"


def test_concentration_vetoes_buy() -> None:
    cfg = _enabled_cfg()
    risk = assess_risk(
        predicted_probability=0.75,
        volatility=0.01,
        drawdown=-0.02,
        position_concentration=0.30,
        model_agreement=1.0,
        config=cfg,
    )
    gate = apply_risk_gate(
        "BUY",
        risk,
        volatility=0.01,
        drawdown=-0.02,
        position_concentration=0.30,
        config=cfg,
    )
    assert gate["signal"] == "HOLD"
    assert gate["action"] == "veto"
    assert any("concentration" in r for r in gate["reasons"])


def test_elevated_score_downgrades_strong_buy_to_buy() -> None:
    # Soft score path only (no hard max_* breaches).
    cfg = _enabled_cfg(max_volatility=None, max_drawdown=None, max_position_concentration=None)
    risk = {
        "risk_score": 0.75,
        "reasons": ["elevated blended risk"],
    }
    gate = apply_risk_gate(
        "STRONG BUY",
        risk,
        volatility=0.02,
        drawdown=-0.05,
        position_concentration=0.05,
        config=cfg,
    )
    assert gate["signal"] == "BUY"
    assert gate["action"] == "downgrade"
    assert gate["original_signal"] == "STRONG BUY"


def test_buy_downgrades_to_hold_on_soft_score() -> None:
    cfg = _enabled_cfg(max_volatility=None, max_drawdown=None, max_position_concentration=None)
    risk = {"risk_score": 0.72, "reasons": []}
    gate = apply_risk_gate("BUY", risk, config=cfg)
    assert gate["signal"] == "HOLD"
    assert gate["action"] == "veto"


def test_sell_signals_not_gated() -> None:
    cfg = _enabled_cfg()
    risk = assess_risk(
        predicted_probability=0.1,
        volatility=0.08,
        drawdown=-0.40,
        position_concentration=0.5,
        config=cfg,
    )
    for signal in ("SELL", "STRONG SELL", "HOLD"):
        gate = apply_risk_gate(signal, risk, volatility=0.08, drawdown=-0.40, position_concentration=0.5, config=cfg)
        assert gate["signal"] == signal
        assert gate["gated"] is False
