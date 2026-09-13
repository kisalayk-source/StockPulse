"""Fundamental features from Finnhub metrics (MVP-4)."""

from __future__ import annotations

from typing import Any

from ml.features.feature_schema import normalize_feature_dict
from ml.features.fundamentals.financial_health import financial_health_features
from ml.features.fundamentals.growth import growth_features
from ml.features.fundamentals.profitability import profitability_features
from ml.features.fundamentals.valuation import valuation_features


def compute_fundamental_features(metrics: dict[str, Any]) -> dict[str, float]:
    """Merge valuation / growth / profitability / health from Finnhub metrics."""
    if not metrics:
        return {}
    values: dict[str, float] = {}
    values.update(valuation_features(metrics))
    values.update(growth_features(metrics))
    values.update(profitability_features(metrics))
    values.update(financial_health_features(metrics))
    return normalize_feature_dict(values)


__all__ = [
    "compute_fundamental_features",
    "financial_health_features",
    "growth_features",
    "profitability_features",
    "valuation_features",
]
