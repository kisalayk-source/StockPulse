"""Financial health features from Finnhub metrics (MVP-4)."""

from __future__ import annotations

from typing import Any

from ml.features.fundamentals._common import pick_metric_features

_KEYS = ("debt_to_equity",)


def financial_health_features(metrics: dict[str, Any]) -> dict[str, float]:
    return pick_metric_features(metrics, _KEYS)
