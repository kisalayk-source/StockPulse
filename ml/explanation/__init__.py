"""Prediction explanation layer (MVP-7) — template always; optional grounded LLM.

Numbers must come from the quantitative structured payload only. LLM narration
(when enabled upstream) rephrases that payload and must never invent figures.
"""

from __future__ import annotations

from typing import Any

LLM_SYSTEM_PROMPT = (
    "You explain a hybrid stock prediction using ONLY the JSON context provided. "
    "Never invent prices, probabilities, filings, fundamentals, model scores, "
    "risk figures, horizons, or signals that are not in the JSON. "
    "You may rephrase and organize the provided numbers into clear prose. "
    "If a field is missing or null, say it is unavailable — do not guess. "
    "End with one short sentence that this is a research signal, not trading advice."
)


def format_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "n/a"


def format_score(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def build_llm_user_content(structured: dict[str, Any], *, template_text: str) -> str:
    """Serialize structured fields for an OpenAI user message."""
    import json

    # Keep payload compact and free of huge nested snapshots.
    allowed = {
        "ticker",
        "signal",
        "probability",
        "raw_probability",
        "risk_score",
        "confidence",
        "horizon",
        "model_predictions",
        "model_agreement",
        "market_regime",
        "technical_score",
        "institutional_score",
        "fundamental_score",
        "calibration_method",
        "risk_gate",
    }
    slim = {key: structured.get(key) for key in allowed if key in structured}
    return (
        "Template summary (figures already verified):\n"
        f"{template_text}\n\n"
        "Structured JSON (authoritative — do not contradict):\n"
        f"{json.dumps(slim, indent=2, default=str)}"
    )


def merge_llm_narration(
    explanation: dict[str, Any],
    llm_text: str | None,
) -> dict[str, Any]:
    """Attach grounded LLM prose when present; otherwise keep the template."""
    base = dict(explanation or {})
    template_text = str(base.get("text") or "")
    if not llm_text or not str(llm_text).strip():
        base["provider"] = "template"
        return base
    narrative = str(llm_text).strip()
    disclaimer = "All figures originate from the quantitative engine; this layer does not invent numbers."
    if disclaimer.lower() not in narrative.lower():
        narrative = f"{narrative}\n\n{disclaimer}"
    return {
        **base,
        "text": narrative,
        "provider": "llm",
        "template_text": template_text,
    }


def explain_prediction(structured: dict[str, Any], *, llm_enabled: bool = False) -> dict[str, Any]:
    """Build a human-readable explanation from structured quantitative fields only.

    ``llm_enabled`` is retained for callers but does **not** change the text or
    falsely label the provider as ``llm``. Backend enrichment may upgrade
    ``provider`` via :func:`merge_llm_narration` after a grounded OpenAI call.
    """
    _ = llm_enabled
    ticker = structured.get("ticker", "?")
    signal = structured.get("signal", "HOLD")
    probability = structured.get("probability")
    risk_score = structured.get("risk_score")
    confidence = structured.get("confidence")
    horizon = structured.get("horizon", "5d")
    regime_raw = structured.get("market_regime")
    if isinstance(regime_raw, dict):
        regime = regime_raw.get("regime")
    else:
        regime = regime_raw

    lines = [
        f"{ticker} is rated {signal} with a {format_pct(probability)} estimated probability "
        f"of positive movement over the {horizon} horizon.",
    ]
    drivers: list[str] = []
    if structured.get("technical_score") is not None:
        drivers.append(f"Technical feature score context: {format_score(structured['technical_score'])}")
    if structured.get("institutional_score") is not None:
        drivers.append(f"Institutional / SEC flow score: {format_score(structured['institutional_score'])}")
    if structured.get("fundamental_score") is not None:
        drivers.append(f"Fundamental score: {format_score(structured['fundamental_score'])}")
    if structured.get("model_agreement") is not None:
        drivers.append(f"Model agreement: {format_pct(structured['model_agreement'])}")
    if confidence is not None:
        drivers.append(f"Signal confidence: {format_pct(confidence)}")
    if regime:
        drivers.append(f"Market regime: {regime}")
    if structured.get("calibration_method"):
        drivers.append(f"Calibration method: {structured['calibration_method']}")

    risks: list[str] = []
    if risk_score is not None:
        risks.append(f"Risk score: {format_score(risk_score)}")
    gate = structured.get("risk_gate") or {}
    if gate.get("gated") and gate.get("action") in {"veto", "downgrade"}:
        original = gate.get("original_signal")
        action = gate.get("action")
        risks.append(f"Risk gate {action}: {original} → {signal}")
        for reason in gate.get("reasons") or []:
            risks.append(str(reason))
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
        "provider": "template",
        "structured": structured,
    }
