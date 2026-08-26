"""Ensemble combination strategies."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from forecasting.core.schema import ForecastResult


def _align_closes(results: Sequence[ForecastResult]) -> pd.DataFrame:
    """Columns = model names, rows = horizon steps; values = close."""
    series: dict[str, pd.Series] = {}
    for result in results:
        close = result.predicted["close"].astype(float).reset_index(drop=True)
        series[result.model_name] = close
    return pd.DataFrame(series)


def normalize_weights(weights: dict[str, float], model_names: Sequence[str]) -> dict[str, float]:
    selected = {name: float(weights.get(name, 0.0)) for name in model_names}
    total = sum(max(0.0, w) for w in selected.values())
    if total <= 0:
        equal = 1.0 / len(model_names) if model_names else 0.0
        return {name: equal for name in model_names}
    return {name: max(0.0, w) / total for name, w in selected.items()}


def weighted_average(
    results: Sequence[ForecastResult],
    weights: dict[str, float],
    *,
    ticker: str | None = None,
) -> ForecastResult:
    if not results:
        raise ValueError("weighted_average requires at least one ForecastResult")
    closes = _align_closes(results)
    names = list(closes.columns)
    norm = normalize_weights(weights, names)
    blended = sum(closes[name] * norm[name] for name in names)
    predicted = pd.DataFrame({"close": blended.astype(float)})

    # Disagreement: cross-model std of final close and mean path std
    final_std = float(closes.iloc[-1].std(ddof=0)) if len(closes) else 0.0
    path_std = float(closes.std(axis=1, ddof=0).mean()) if len(closes) else 0.0

    ticker_out = ticker or results[0].ticker
    return ForecastResult(
        model_name="ensemble",
        ticker=ticker_out,
        predicted=predicted,
        latency_ms=float(sum(r.latency_ms for r in results)),
        meta={
            "strategy": "weighted_average",
            "weights": norm,
            "members": names,
            "disagreement": {
                "final_close_std": final_std,
                "mean_path_std": path_std,
            },
        },
    )


def inverse_error_weights(
    recent_mae: dict[str, float],
    *,
    floor: float = 1e-8,
) -> dict[str, float]:
    """Weight each model by 1/MAE over a trailing window."""
    raw = {name: 1.0 / max(floor, float(mae)) for name, mae in recent_mae.items()}
    return normalize_weights(raw, list(raw.keys()))


def inverse_error_average(
    results: Sequence[ForecastResult],
    recent_mae: dict[str, float],
    *,
    ticker: str | None = None,
) -> ForecastResult:
    weights = inverse_error_weights(recent_mae)
    out = weighted_average(results, weights, ticker=ticker)
    out.meta["strategy"] = "inverse_error"
    out.meta["recent_mae"] = dict(recent_mae)
    return out


def stacking_combine(
    results: Sequence[ForecastResult],
    *,
    coefficients: dict[str, float] | None = None,
    intercept: float = 0.0,
    ticker: str | None = None,
) -> ForecastResult:
    """Linear stacking: blend = intercept + sum(coef_i * model_i).

    If coefficients are missing, fall back to equal-weight average.
    """
    if not results:
        raise ValueError("stacking_combine requires at least one ForecastResult")
    closes = _align_closes(results)
    names = list(closes.columns)
    if not coefficients:
        equal = {name: 1.0 / len(names) for name in names}
        out = weighted_average(results, equal, ticker=ticker)
        out.meta["strategy"] = "stacking"
        out.meta["fallback"] = "equal_weight"
        return out

    blended = pd.Series(intercept, index=closes.index, dtype=float)
    used: dict[str, float] = {}
    for name in names:
        coef = float(coefficients.get(name, 0.0))
        used[name] = coef
        blended = blended + closes[name] * coef

    return ForecastResult(
        model_name="ensemble",
        ticker=ticker or results[0].ticker,
        predicted=pd.DataFrame({"close": blended.astype(float)}),
        latency_ms=float(sum(r.latency_ms for r in results)),
        meta={
            "strategy": "stacking",
            "coefficients": used,
            "intercept": intercept,
            "members": names,
            "disagreement": {
                "final_close_std": float(closes.iloc[-1].std(ddof=0)),
                "mean_path_std": float(closes.std(axis=1, ddof=0).mean()),
            },
        },
    )


def fit_stacking_ridge(
    member_preds: np.ndarray,
    actuals: np.ndarray,
    *,
    member_names: Sequence[str],
    alpha: float = 1.0,
) -> tuple[dict[str, float], float]:
    """Fit ridge regression on stacked predictions.

    member_preds: shape (n_samples, n_models)
    actuals: shape (n_samples,)
    """
    from numpy.linalg import lstsq

    x = np.asarray(member_preds, dtype=float)
    y = np.asarray(actuals, dtype=float).reshape(-1)
    if x.ndim != 2 or x.shape[0] != y.shape[0]:
        raise ValueError("member_preds/actuals shape mismatch")
    # Augment with intercept column; ridge via Tikhonov on slopes only
    ones = np.ones((x.shape[0], 1))
    design = np.hstack([ones, x])
    # Simple ridge: solve (A'A + λI) β = A'y with λ on non-intercept
    ata = design.T @ design
    penalty = np.eye(ata.shape[0]) * alpha
    penalty[0, 0] = 0.0
    beta, *_ = lstsq(ata + penalty, design.T @ y, rcond=None)
    intercept = float(beta[0])
    coefficients = {name: float(beta[i + 1]) for i, name in enumerate(member_names)}
    return coefficients, intercept


def combine(
    results: Sequence[ForecastResult],
    *,
    strategy: str = "weighted_average",
    weights: dict[str, float] | None = None,
    recent_mae: dict[str, float] | None = None,
    stacking_coefficients: dict[str, float] | None = None,
    stacking_intercept: float = 0.0,
    ticker: str | None = None,
) -> ForecastResult:
    """Dispatch to a named ensemble strategy."""
    if strategy == "inverse_error":
        if not recent_mae:
            raise ValueError("inverse_error strategy requires recent_mae")
        return inverse_error_average(results, recent_mae, ticker=ticker)
    if strategy == "stacking":
        return stacking_combine(
            results,
            coefficients=stacking_coefficients,
            intercept=stacking_intercept,
            ticker=ticker,
        )
    return weighted_average(results, weights or {}, ticker=ticker)
