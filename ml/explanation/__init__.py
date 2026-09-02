"""LLM / template explanation layer — never invents numbers."""

from __future__ import annotations

from typing import Any


def explain_prediction(structured: dict[str, Any], *, llm_enabled: bool = False) -> dict[str, Any]:
    """Build a human-readable explanation from structured quantitative fields only."""
    ticker = structured.get("ticker", "?")
    signal = structured.get("signal", "HOLD")
    probability = structured.get("probability")
    risk_score = structured.get("risk_score")
    horizon = structured.get("horizon", "5d")
    regime = (structured.get("market_regime") or {}).get("regime") if isinstance(structured.get("market_regime"), dict) else structured.get("market_regime")

    lines = [
        f"{ticker} is rated {signal} with a {format_pct(probability)} estimated probability "
        f"of positive movement over the {horizon} horizon.",
    ]
    drivers = []
    if structured.get("technical_score") is not None:
        drivers.append(f"Technical feature score context: {structured['technical_score']}")
    if structured.get("model_agreement") is not None:
        drivers.append(f"Model agreement: {format_pct(structured['model_agreement'])}")
    if regime:
        drivers.append(f"Market regime: {regime}")
    risks = []
    if risk_score is not None:
        risks.append(f"Risk score: {risk_score}")
    members = structured.get("model_predictions") or {}
    if members:
        drivers.append(
            "Model probabilities: "
            + ", ".join(f"{name}={format_pct(value)}" for name, value in members.items())
        )

    text = lines[0]
    if drivers:
        text += "\n\nPrimary drivers:\n" + "\n".join(f"- {item}" for item in drivers)
    if risks:
        text += "\n\nRisks:\n" + "\n".join(f"- {item}" for item in risks)
    text += "\n\nAll figures originate from the quantitative engine; this layer does not invent numbers."

    return {
        "text": text,
        "provider": "llm" if llm_enabled else "template",
        "structured": structured,
    }


def format_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "n/a"
