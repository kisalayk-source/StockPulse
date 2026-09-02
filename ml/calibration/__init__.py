"""Probability calibration (MVP-2 hooks; identity for MVP-1)."""

from __future__ import annotations

from typing import Any

import numpy as np


def calibrate_probability(
    raw_probability: float,
    *,
    method: str = "identity",
    calibrator: Any | None = None,
) -> float:
    p = float(np.clip(raw_probability, 0.0, 1.0))
    if method == "identity" or calibrator is None:
        return p
    if method in {"platt", "isotonic"}:
        # Calibrator objects are fitted in MVP-2+.
        transformed = calibrator.predict([p])
        return float(np.clip(transformed[0], 0.0, 1.0))
    raise ValueError(f"unsupported calibration method: {method}")


def calibration_metrics(y_true: list[float], y_prob: list[float]) -> dict[str, float]:
    """Compute Brier score and log loss for evaluation scaffolding."""
    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(y_prob, dtype=float), 1e-7, 1 - 1e-7)
    if len(y) == 0:
        return {"brier_score": float("nan"), "log_loss": float("nan")}
    brier = float(np.mean((p - y) ** 2))
    log_loss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return {"brier_score": brier, "log_loss": log_loss}
