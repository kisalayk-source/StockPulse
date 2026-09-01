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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
