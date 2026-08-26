"""Ensemble package."""

from forecasting.ensemble.combine import combine_results, forecast_ensemble, run_models
from forecasting.ensemble.strategies import (
    combine,
    fit_stacking_ridge,
    inverse_error_weights,
    weighted_average,
)

__all__ = [
    "combine",
    "combine_results",
    "fit_stacking_ridge",
    "forecast_ensemble",
    "inverse_error_weights",
    "run_models",
    "weighted_average",
]
