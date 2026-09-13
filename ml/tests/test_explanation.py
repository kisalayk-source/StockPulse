"""MVP-7 explanation template + merge helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.explanation import (
    build_llm_user_content,
    explain_prediction,
    merge_llm_narration,
)


def _structured() -> dict:
    return {
        "ticker": "AAPL",
        "signal": "BUY",
        "probability": 0.72,
        "raw_probability": 0.71,
        "risk_score": 0.31,
        "confidence": 0.76,
        "horizon": "5d",
        "model_predictions": {"xgboost": 0.70, "lightgbm": 0.74},
        "model_agreement": 0.9,
        "market_regime": {"regime": "BULL"},
        "technical_score": 0.62,
        "institutional_score": 0.55,
        "fundamental_score": 0.58,
        "calibration_method": "platt",
        "risk_gate": {"gated": False, "action": "none"},
    }


def test_template_uses_only_structured_figures() -> None:
    explanation = explain_prediction(_structured())
    assert explanation["provider"] == "template"
    text = explanation["text"]
    assert "AAPL" in text
    assert "BUY" in text
    assert "72%" in text
    assert "Technical feature score context: 0.62" in text
    assert "Institutional / SEC flow score: 0.55" in text
    assert "Fundamental score: 0.58" in text
    assert "xgboost=70%" in text
    assert "does not invent numbers" in text
    # llm_enabled must not falsely label provider
    assert explain_prediction(_structured(), llm_enabled=True)["provider"] == "template"


def test_risk_gate_reasons_appear_in_template() -> None:
    structured = _structured()
    structured["signal"] = "HOLD"
    structured["risk_gate"] = {
        "gated": True,
        "action": "veto",
        "original_signal": "BUY",
        "reasons": ["elevated volatility"],
    }
    text = explain_prediction(structured)["text"]
    assert "Risk gate veto: BUY → HOLD" in text
    assert "elevated volatility" in text


def test_merge_llm_narration_upgrades_provider() -> None:
    base = explain_prediction(_structured())
    merged = merge_llm_narration(base, "AAPL looks constructive at 72% over 5d based on the provided scores.")
    assert merged["provider"] == "llm"
    assert "72%" in merged["text"]
    assert "template_text" in merged
    assert merged["template_text"] == base["text"]
    assert "does not invent numbers" in merged["text"].lower()


def test_merge_llm_narration_keeps_template_on_empty() -> None:
    base = explain_prediction(_structured())
    merged = merge_llm_narration(base, "  ")
    assert merged["provider"] == "template"
    assert merged["text"] == base["text"]


def test_build_llm_user_content_is_slim() -> None:
    structured = _structured()
    structured["feature_snapshot"] = {"technical": {"rsi": 55}, "huge": list(range(100))}
    content = build_llm_user_content(structured, template_text="template")
    assert "Template summary" in content
    assert '"ticker": "AAPL"' in content or '"ticker": "AAPL"' in content.replace("'", '"')
    assert "feature_snapshot" not in content
    assert "huge" not in content
