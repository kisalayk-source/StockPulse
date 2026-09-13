"""Classification / calibration metrics for hybrid prediction backtests."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from ml.calibration import calibration_metrics


def classification_metrics(
    y_true: Sequence[int | float],
    y_pred: Sequence[int | float] | None = None,
    y_prob: Sequence[float] | None = None,
) -> dict[str, float]:
    """Accuracy, hit-rate, AUC, Brier, and log-loss for binary direction labels."""
    y = np.asarray(y_true, dtype=float)
    if len(y) == 0:
        return {
            "n": 0.0,
            "accuracy": float("nan"),
            "hit_rate": float("nan"),
            "auc": float("nan"),
            "brier_score": float("nan"),
            "log_loss": float("nan"),
            "positive_rate": float("nan"),
        }

    if y_prob is None:
        probs = np.asarray(y_pred if y_pred is not None else y, dtype=float)
        # treat hard labels as degenerate probabilities
        probs = np.clip(probs.astype(float), 0.0, 1.0)
    else:
        probs = np.clip(np.asarray(y_prob, dtype=float), 1e-7, 1.0 - 1e-7)

    if y_pred is None:
        preds = (probs >= 0.5).astype(int)
    else:
        preds = np.asarray(y_pred, dtype=int)

    accuracy = float(np.mean(preds == y.astype(int)))
    # Hit rate = directional accuracy on non-flat labels (same as accuracy for binary 0/1).
    hit_rate = accuracy
    positive_rate = float(np.mean(y))

    cal = calibration_metrics(y.tolist(), probs.tolist())
    auc = _roc_auc(y, probs)

    return {
        "n": float(len(y)),
        "accuracy": accuracy,
        "hit_rate": hit_rate,
        "auc": auc,
        "brier_score": float(cal["brier_score"]),
        "log_loss": float(cal["log_loss"]),
        "positive_rate": positive_rate,
    }


def aggregate_fold_metrics(fold_metrics: list[dict[str, float]]) -> dict[str, float]:
    """Mean metrics across folds, weighted by sample count when present."""
    if not fold_metrics:
        return {"n_folds": 0.0}
    keys = sorted({k for row in fold_metrics for k in row if k != "n"})
    total_n = sum(float(row.get("n") or 0.0) for row in fold_metrics)
    out: dict[str, float] = {"n_folds": float(len(fold_metrics)), "n": total_n}
    for key in keys:
        values = [(float(row[key]), float(row.get("n") or 0.0)) for row in fold_metrics if key in row]
        finite = [(v, w) for v, w in values if v == v]  # drop NaN
        if not finite:
            out[key] = float("nan")
            continue
        if total_n > 0 and any(w > 0 for _, w in finite):
            out[key] = float(sum(v * w for v, w in finite) / sum(w for _, w in finite))
        else:
            out[key] = float(np.mean([v for v, _ in finite]))
    return out


def information_coefficient(y_true_return: Sequence[float], y_prob: Sequence[float]) -> float:
    """Spearman-like rank IC between predicted P(up) and realized forward return."""
    a = np.asarray(y_true_return, dtype=float)
    b = np.asarray(y_prob, dtype=float)
    if len(a) < 3 or len(a) != len(b):
        return float("nan")
    # Pearson on ranks ≈ Spearman
    ra = a.argsort().argsort().astype(float)
    rb = b.argsort().argsort().astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def _roc_auc(y: np.ndarray, probs: np.ndarray) -> float:
    if len(np.unique(y)) < 2:
        return float("nan")
    try:
        from sklearn.metrics import roc_auc_score

        return float(roc_auc_score(y.astype(int), probs))
    except Exception:
        return float("nan")


def summarize_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    """Coerce a metrics mapping to float values for registry storage."""
    out: dict[str, float] = {}
    for key, value in metrics.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != number:  # NaN
            continue
        out[str(key)] = number
    return out
