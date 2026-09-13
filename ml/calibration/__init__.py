"""Probability calibration (MVP-2): identity, Platt, or isotonic."""

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
        transformed = calibrator.predict(np.asarray([p], dtype=float))
        return float(np.clip(transformed[0], 0.0, 1.0))
    raise ValueError(f"unsupported calibration method: {method}")


def fit_calibrator(
    y_true: list[float] | np.ndarray,
    y_prob: list[float] | np.ndarray,
    method: str,
) -> Any | None:
    """Fit a calibrator on chronological holdout probabilities.

    Returns ``None`` for identity or when the holdout is too thin / single-class.
    """
    method = str(method or "identity").lower()
    if method == "identity":
        return None

    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(y_prob, dtype=float), 1e-7, 1 - 1e-7)
    if len(y) < 8 or len(np.unique(y)) < 2:
        return None

    if method == "platt":
        from sklearn.linear_model import LogisticRegression

        # Platt scaling: logistic regression of labels on logit(prob).
        logit = np.log(p / (1.0 - p)).reshape(-1, 1)
        clf = LogisticRegression(solver="lbfgs", max_iter=200)
        clf.fit(logit, y.astype(int))
        return _PlattWrapper(clf)

    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression

        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(p, y)
        return iso

    raise ValueError(f"unsupported calibration method: {method}")


class _PlattWrapper:
    """Apply logistic regression in logit-probability space."""

    def __init__(self, clf: Any) -> None:
        self.clf = clf

    def predict(self, probs: np.ndarray | list[float]) -> np.ndarray:
        p = np.clip(np.asarray(probs, dtype=float), 1e-7, 1 - 1e-7)
        logit = np.log(p / (1.0 - p)).reshape(-1, 1)
        return self.clf.predict_proba(logit)[:, 1]


def calibration_metrics(y_true: list[float], y_prob: list[float]) -> dict[str, float]:
    """Compute Brier score and log loss for evaluation scaffolding."""
    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(y_prob, dtype=float), 1e-7, 1 - 1e-7)
    if len(y) == 0:
        return {"brier_score": float("nan"), "log_loss": float("nan")}
    brier = float(np.mean((p - y) ** 2))
    log_loss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return {"brier_score": brier, "log_loss": log_loss}
