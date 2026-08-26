"""Adapter schema conformance helper tests."""

from __future__ import annotations

import pandas as pd

from forecasting.adapters.kronos_adapter import KronosAdapter
from forecasting.core.schema import ForecastInput, assert_forecast_result
from forecasting.tests.test_kronos_adapter import _MockPredictor, _ohlcv


def test_adapters_conform_to_schema():
    """Every mocked adapter returns an identical ForecastResult shape."""
    kronos = KronosAdapter(predictor=_MockPredictor())
    inp = ForecastInput(ticker="X", ohlcv=_ohlcv(), horizon=4, timeframe="1Day")
    results = [kronos.predict(inp)]

    # Chronos mock inline to avoid circular imports
    from forecasting.adapters.chronos_adapter import ChronosAdapter
    from forecasting.tests.test_chronos_adapter import _MockPipeline

    chronos = ChronosAdapter(pipeline=_MockPipeline())
    results.append(chronos.predict(inp))

    for result in results:
        assert_forecast_result(result, horizon=4)
        assert "close" in result.predicted.columns
        assert result.ticker == "X"
        assert isinstance(result.meta, dict)
