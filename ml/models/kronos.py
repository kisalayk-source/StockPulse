"""Kronos directional adapter (MVP-2).

Maps path-forecast outcomes into P(up). Does not invent signals from technical rules.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml.models.base import ForecastModel


def probability_from_path(
    path_payload: dict[str, Any] | None,
    *,
    volatility: float | None = None,
    horizon_bars: int = 1,
) -> float:
    """Convert a Kronos/ensemble path payload into P(price up).

    Uses ``trend.forecast_change`` (fractional) scaled by volatility via a sigmoid.
    One-day volatility is stretched by ``sqrt(horizon_bars)`` so a multi-day
    move is not treated as a one-day shock.
    """
    if not path_payload:
        return 0.5
    trend = path_payload.get("trend") if isinstance(path_payload.get("trend"), dict) else {}
    change = trend.get("net_forecast_change")
    if change is None:
        change = trend.get("forecast_change")
    try:
        change_f = float(change)
    except (TypeError, ValueError):
        change_f = 0.0

    vol = volatility
    if vol is None or not np.isfinite(vol) or vol <= 0:
        # Fallback: std of historical close returns if present.
        hist = path_payload.get("historical") or []
        closes = []
        for row in hist:
            if isinstance(row, dict) and row.get("close") is not None:
                try:
                    closes.append(float(row["close"]))
                except (TypeError, ValueError):
                    continue
        if len(closes) >= 5:
            rets = np.diff(np.log(np.clip(closes, 1e-9, None)))
            vol = float(np.std(rets)) if len(rets) else 0.02
        else:
            vol = 0.02
    vol = max(float(vol), 1e-4)
    bars = max(1, int(horizon_bars))
    z = change_f / (vol * float(np.sqrt(bars)))
    return float(1.0 / (1.0 + np.exp(-z)))


class KronosModel(ForecastModel):
    name = "kronos"
    version = "1.0"

    def __init__(self, *, scale: float = 1.0) -> None:
        self.scale = float(scale)
        self._last_path: dict[str, Any] | None = None
        self._horizon_bars = 1

    def train(self, dataset: pd.DataFrame) -> None:
        # Pretrained foundation weights; fine-tune path is out of MVP-2 directional scope.
        _ = dataset

    def predict(self, features: pd.DataFrame | dict[str, float]) -> Any:
        return int(self.predict_probability(features) >= 0.5)

    def predict_probability(self, features: pd.DataFrame | dict[str, float]) -> float:
        """Prefer ``set_path`` / ``probability_from_path``; features unused for direction."""
        _ = features
        return probability_from_path(self._last_path, horizon_bars=self._horizon_bars)

    def set_path(
        self,
        path_payload: dict[str, Any] | None,
        *,
        volatility: float | None = None,
        horizon_bars: int = 1,
    ) -> float:
        self._last_path = path_payload
        self._horizon_bars = max(1, int(horizon_bars))
        return probability_from_path(path_payload, volatility=volatility, horizon_bars=self._horizon_bars)
