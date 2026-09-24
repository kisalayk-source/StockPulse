"""Ensemble orchestration."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from forecasting.core.base import ForecastModel
from forecasting.core.schema import ForecastInput, ForecastResult, assert_forecast_result
from forecasting.ensemble.strategies import combine

logger = logging.getLogger("forecasting.ensemble")

# Models whose load()/import failed once. Later calls skip them for this process.
_FAILED_MODELS: set[str] = set()


def reset_failed_models() -> None:
    """Clear the process-level skip set. Tests use this."""
    _FAILED_MODELS.clear()


def _is_load_failure(exc: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (ImportError, ModuleNotFoundError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def run_models(
    models: Sequence[ForecastModel],
    inp: ForecastInput,
    *,
    skip_unsupported: bool = True,
) -> list[ForecastResult]:
    """Run each model that supports ``inp``; skip + log otherwise."""
    results: list[ForecastResult] = []
    for model in models:
        name = str(getattr(model, "name", model))
        if name in _FAILED_MODELS:
            continue
        if not model.supports(inp):
            msg = f"skipping {name} (supports=False)"
            if skip_unsupported:
                logger.info(msg)
                continue
            raise ValueError(msg)
        try:
            result = model.predict(inp)
            assert_forecast_result(result, horizon=inp.horizon)
            results.append(result)
        except Exception as exc:
            if _is_load_failure(exc):
                _FAILED_MODELS.add(name)
                logger.warning("dropping model %s after load failure: %s", name, exc)
                continue
            logger.exception("model %s failed during predict", name)
            if not skip_unsupported:
                raise
    return results


def combine_results(
    results: Sequence[ForecastResult],
    *,
    strategy: str = "weighted_average",
    weights: dict[str, float] | None = None,
    recent_mae: dict[str, float] | None = None,
    stacking_coefficients: dict[str, float] | None = None,
    stacking_intercept: float = 0.0,
    ticker: str | None = None,
) -> ForecastResult:
    return combine(
        results,
        strategy=strategy,
        weights=weights,
        recent_mae=recent_mae,
        stacking_coefficients=stacking_coefficients,
        stacking_intercept=stacking_intercept,
        ticker=ticker,
    )


def forecast_ensemble(
    models: Sequence[ForecastModel],
    inp: ForecastInput,
    *,
    strategy: str = "weighted_average",
    weights: dict[str, float] | None = None,
    recent_mae: dict[str, float] | None = None,
    stacking_coefficients: dict[str, float] | None = None,
    stacking_intercept: float = 0.0,
) -> tuple[list[ForecastResult], ForecastResult | None]:
    """Run active models and combine. Returns (per_model, ensemble_or_none)."""
    per_model = run_models(models, inp)
    if not per_model:
        return [], None
    ensemble = combine_results(
        per_model,
        strategy=strategy,
        weights=weights,
        recent_mae=recent_mae,
        stacking_coefficients=stacking_coefficients,
        stacking_intercept=stacking_intercept,
        ticker=inp.ticker,
    )
    return per_model, ensemble
