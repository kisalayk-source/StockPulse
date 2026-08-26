"""Forecast evaluation metrics (path-oriented research harness)."""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


def directional_accuracy(predicted: pd.Series | np.ndarray, actual: pd.Series | np.ndarray) -> float:
    """Fraction of steps where sign(pred_change) matches sign(actual_change).

    Uses first-to-last change when length==1 relative to a prior last_close
    is not available — for multi-step paths, compares step-to-step returns.
    """
    pred = np.asarray(predicted, dtype=float).reshape(-1)
    act = np.asarray(actual, dtype=float).reshape(-1)
    n = min(len(pred), len(act))
    if n < 2:
        if n == 1:
            return float(np.sign(pred[0]) == np.sign(act[0])) if pred[0] != 0 or act[0] != 0 else 1.0
        return float("nan")
    pred_ret = np.diff(pred[:n])
    act_ret = np.diff(act[:n])
    mask = act_ret != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.sign(pred_ret[mask]) == np.sign(act_ret[mask])))


def mae(predicted: pd.Series | np.ndarray, actual: pd.Series | np.ndarray) -> float:
    pred = np.asarray(predicted, dtype=float).reshape(-1)
    act = np.asarray(actual, dtype=float).reshape(-1)
    n = min(len(pred), len(act))
    if n == 0:
        return float("nan")
    return float(np.mean(np.abs(pred[:n] - act[:n])))


def rmse(predicted: pd.Series | np.ndarray, actual: pd.Series | np.ndarray) -> float:
    pred = np.asarray(predicted, dtype=float).reshape(-1)
    act = np.asarray(actual, dtype=float).reshape(-1)
    n = min(len(pred), len(act))
    if n == 0:
        return float("nan")
    return float(np.sqrt(np.mean((pred[:n] - act[:n]) ** 2)))


def rank_ic(predicted_scores: Sequence[float], actual_scores: Sequence[float]) -> float:
    """Spearman rank correlation (cross-sectional RankIC)."""
    pred = pd.Series(list(predicted_scores), dtype=float)
    act = pd.Series(list(actual_scores), dtype=float)
    if len(pred) < 2:
        return float("nan")
    return float(pred.rank().corr(act.rank(), method="pearson"))


def sharpe_of_signal(
    predicted_returns: Sequence[float],
    actual_returns: Sequence[float],
    *,
    periods_per_year: float = 252.0,
) -> float:
    """Simple signal Sharpe: position = sign(pred), return = position * actual."""
    pred = np.asarray(predicted_returns, dtype=float)
    act = np.asarray(actual_returns, dtype=float)
    n = min(len(pred), len(act))
    if n < 2:
        return float("nan")
    positions = np.sign(pred[:n])
    pnl = positions * act[:n]
    vol = float(np.std(pnl, ddof=1))
    if vol <= 0:
        return float("nan")
    return float(np.mean(pnl) / vol * np.sqrt(periods_per_year))


def path_metrics(
    predicted_close: pd.Series | np.ndarray,
    actual_close: pd.Series | np.ndarray,
    *,
    last_close: float | None = None,
) -> dict[str, float]:
    """Bundle of common path metrics including horizon directional hit."""
    pred = np.asarray(predicted_close, dtype=float).reshape(-1)
    act = np.asarray(actual_close, dtype=float).reshape(-1)
    out = {
        "mae": mae(pred, act),
        "rmse": rmse(pred, act),
        "directional_accuracy": directional_accuracy(pred, act),
    }
    if last_close is not None and last_close != 0 and len(pred) and len(act):
        pred_chg = float(pred[-1] / last_close - 1.0)
        act_chg = float(act[-1] / last_close - 1.0)
        out["horizon_dir_hit"] = float(np.sign(pred_chg) == np.sign(act_chg))
        out["pred_horizon_return"] = pred_chg
        out["actual_horizon_return"] = act_chg
    return out
