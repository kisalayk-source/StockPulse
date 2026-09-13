"""Shared helpers for fundamental feature builders."""

from __future__ import annotations

from typing import Any

from ml.features.feature_schema import normalize_feature_dict


def pick_metric_features(metrics: dict[str, Any], keys: tuple[str, ...]) -> dict[str, float]:
    """Passthrough selected Finnhub metric keys; drop nulls via normalize."""
    values: dict[str, float | None] = {}
    for key in keys:
        if key not in metrics:
            continue
        raw = metrics.get(key)
        if raw is None:
            values[key] = None
            continue
        try:
            values[key] = float(raw)
        except (TypeError, ValueError):
            values[key] = None
    return normalize_feature_dict(values)
