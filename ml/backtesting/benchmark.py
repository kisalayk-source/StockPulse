"""Benchmark helpers for hybrid prediction evaluation (MVP-6)."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from ml.backtesting.metrics import classification_metrics


def buy_and_hold_return(closes: Sequence[float]) -> float:
    if len(closes) < 2 or closes[0] == 0:
        return 0.0
    return float(closes[-1] / closes[0] - 1.0)


def always_long_metrics(y_true: Sequence[int | float]) -> dict[str, float]:
    """Baseline that always predicts up (probability 1.0)."""
    y = list(y_true)
    probs = [1.0] * len(y)
    preds = [1] * len(y)
    return classification_metrics(y, preds, probs)


def compare_to_benchmarks(
    *,
    closes: Sequence[float] | None = None,
    y_true: Sequence[int | float] | None = None,
    model_metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compare model metrics against buy-and-hold and always-long baselines."""
    out: dict[str, Any] = {"model": dict(model_metrics or {})}
    if closes is not None and len(closes) >= 2:
        out["buy_and_hold_return"] = buy_and_hold_return(closes)
    if y_true is not None and len(y_true) > 0:
        baseline = always_long_metrics(y_true)
        out["always_long"] = baseline
        if model_metrics:
            model_acc = float(model_metrics.get("accuracy") or model_metrics.get("hit_rate") or np.nan)
            base_acc = float(baseline.get("accuracy") or np.nan)
            if model_acc == model_acc and base_acc == base_acc:
                out["accuracy_vs_always_long"] = model_acc - base_acc
    return out
