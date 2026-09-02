from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

INSIDER_CODE_MAP: dict[str, str] = {
    "P": "DISCRETIONARY_BUY",
    "S": "DISCRETIONARY_SELL",
    "A": "COMPENSATION",
    "M": "OPTION_EXERCISE",
    "F": "TAX_WITHHOLDING",
}

INSTITUTIONAL_CLASSIFICATIONS = {
    "NEW_POSITION": 1.0,
    "INCREASED": 0.7,
    "UNCHANGED": 0.0,
    "DECREASED": -0.7,
    "EXITED": -1.0,
}


def classify_institutional_change(previous: float, current: float) -> str:
    if previous <= 0 and current > 0:
        return "NEW_POSITION"
    if previous > 0 and current <= 0:
        return "EXITED"
    if current > previous:
        return "INCREASED"
    if current < previous:
        return "DECREASED"
    return "UNCHANGED"


def institutional_change_pct(previous: float, current: float) -> float | None:
    if previous <= 0:
        return None if current <= 0 else 100.0
    return ((current - previous) / previous) * 100.0


def classify_insider_transaction(code: str) -> str:
    return INSIDER_CODE_MAP.get(code.upper()[:1], "OTHER")


def is_discretionary_insider(normalized_type: str) -> bool:
    return normalized_type in {"DISCRETIONARY_BUY", "DISCRETIONARY_SELL"}


def classify_beneficial_ownership_event(
    previous_pct: float | None,
    current_pct: float | None,
) -> str:
    prev = previous_pct or 0.0
    curr = current_pct or 0.0
    if prev <= 0 and curr > 0:
        return "NEW_MAJOR_HOLDER"
    if prev > 0 and curr <= 0:
        return "OWNERSHIP_EXIT"
    if curr > prev:
        return "OWNERSHIP_INCREASE"
    if curr < prev:
        return "OWNERSHIP_DECREASE"
    return "OWNERSHIP_UNCHANGED"


def polarity_for_institutional(classification: str, config: dict[str, Any]) -> float:
    signals = config.get("institutional_signal", INSTITUTIONAL_CLASSIFICATIONS)
    key = classification.lower()
    if key in signals:
        return float(signals[key])
    return float(signals.get(classification, 0.0))


def polarity_for_insider(normalized_type: str) -> float:
    if normalized_type == "DISCRETIONARY_BUY":
        return 1.0
    if normalized_type == "DISCRETIONARY_SELL":
        return -1.0
    return 0.0


def polarity_for_major_holder(event_type: str) -> float:
    if event_type in {"NEW_MAJOR_HOLDER", "OWNERSHIP_INCREASE"}:
        return 0.5
    if event_type in {"OWNERSHIP_DECREASE", "OWNERSHIP_EXIT"}:
        return -0.5
    return 0.0


INSIDER_ACTION_LABELS = {
    "DISCRETIONARY_BUY": "Bought",
    "DISCRETIONARY_SELL": "Sold",
    "COMPENSATION": "Award / compensation",
    "OPTION_EXERCISE": "Option exercise",
    "TAX_WITHHOLDING": "Tax withholding",
    "OTHER": "Other transaction",
}

INSTITUTIONAL_ACTION_LABELS = {
    "NEW_POSITION": "New investment",
    "INCREASED": "Increased position",
    "DECREASED": "Reduced position",
    "EXITED": "Sold entire position",
    "UNCHANGED": "Unchanged position",
}

OWNERSHIP_ACTION_LABELS = {
    "NEW_MAJOR_HOLDER": "New major holder",
    "OWNERSHIP_INCREASE": "Increased stake",
    "OWNERSHIP_DECREASE": "Reduced stake",
    "OWNERSHIP_EXIT": "Exited position",
    "OWNERSHIP_UNCHANGED": "Ownership update",
}


def insider_action_label(normalized_type: str) -> str:
    return INSIDER_ACTION_LABELS.get(normalized_type, normalized_type.replace("_", " ").title())


def institutional_action_label(classification: str) -> str:
    return INSTITUTIONAL_ACTION_LABELS.get(classification, classification.replace("_", " ").title())


def ownership_action_label(event_type: str | None) -> str:
    if not event_type:
        return "Ownership filing"
    return OWNERSHIP_ACTION_LABELS.get(event_type, event_type.replace("_", " ").title())


def action_tone_for_insider(normalized_type: str) -> str:
    if normalized_type == "DISCRETIONARY_BUY":
        return "positive"
    if normalized_type == "DISCRETIONARY_SELL":
        return "negative"
    return "neutral"


def action_tone_for_institutional(classification: str) -> str:
    if classification in {"NEW_POSITION", "INCREASED"}:
        return "positive"
    if classification in {"DECREASED", "EXITED"}:
        return "negative"
    return "neutral"


def action_tone_for_ownership(event_type: str | None) -> str:
    if event_type in {"NEW_MAJOR_HOLDER", "OWNERSHIP_INCREASE"}:
        return "positive"
    if event_type in {"OWNERSHIP_DECREASE", "OWNERSHIP_EXIT"}:
        return "negative"
    return "neutral"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
