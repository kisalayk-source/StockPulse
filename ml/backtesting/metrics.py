"""Backtest metrics scaffold (MVP-6)."""

from __future__ import annotations

from typing import Any


def classification_metrics(y_true: list[int], y_pred: list[int], y_prob: list[float]) -> dict[str, float]:
    _ = y_true, y_pred, y_prob
    return {}
