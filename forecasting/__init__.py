"""Model-agnostic financial forecasting research package."""

from forecasting.core.base import ForecastModel
from forecasting.core.schema import ForecastInput, ForecastResult, assert_forecast_result

__all__ = [
    "ForecastInput",
    "ForecastModel",
    "ForecastResult",
    "assert_forecast_result",
]
