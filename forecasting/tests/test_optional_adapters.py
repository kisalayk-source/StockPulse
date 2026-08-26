"""TimesFM and Lag-Llama adapter tests (mocked; optional live via env)."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from forecasting.adapters.lag_llama_adapter import LagLlamaAdapter
from forecasting.adapters.timesfm_adapter import TimesFMAdapter
from forecasting.core.schema import ForecastInput, ForecastResult, assert_forecast_result


def _ohlcv(n: int = 64) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=n, freq="B", tz="UTC")
    close = pd.Series(np.linspace(100, 130, n), dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )


class _MockTimesFM:
    def forecast(self, series_list, freq):
        closes = np.asarray(series_list[0], dtype=float)
        last = float(closes[-1])
        horizon = 16
        point = np.array([[last * (1 + 0.001 * (i + 1)) for i in range(horizon)]])
        return point, None


def test_timesfm_mock():
    adapter = TimesFMAdapter(model=_MockTimesFM())
    inp = ForecastInput(ticker="SPY", ohlcv=_ohlcv(), horizon=5)
    assert adapter.supports(inp) is True
    result = adapter.predict(inp)
    assert_forecast_result(result, horizon=5)
    assert result.model_name == "timesfm"


def test_lag_llama_injected_predictor():
    def _pred(inp: ForecastInput) -> ForecastResult:
        last = float(inp.ohlcv["close"].iloc[-1])
        return ForecastResult(
            model_name="lag_llama",
            ticker=inp.ticker,
            predicted=pd.DataFrame({"close": [last] * inp.horizon}),
            quantiles={
                0.1: pd.DataFrame({"close": [last * 0.99] * inp.horizon}),
                0.9: pd.DataFrame({"close": [last * 1.01] * inp.horizon}),
            },
            meta={"checkpoint": "mock"},
        )

    adapter = LagLlamaAdapter(predictor=_pred)
    inp = ForecastInput(ticker="SPY", ohlcv=_ohlcv(), horizon=4)
    result = adapter.predict(inp)
    assert_forecast_result(result, horizon=4)
    assert result.quantiles is not None


def test_timesfm_optional_live():
    pytest.importorskip("timesfm")
    if os.environ.get("TIMESFM_LIVE") != "1":
        pytest.skip("set TIMESFM_LIVE=1 to download TimesFM weights")
    adapter = TimesFMAdapter()
    inp = ForecastInput(ticker="SPY", ohlcv=_ohlcv(128), horizon=8)
    result = adapter.predict(inp)
    assert_forecast_result(result, horizon=8)
