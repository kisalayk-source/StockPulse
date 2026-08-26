"""ChronosAdapter tests — skip when chronos package is missing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forecasting.adapters.chronos_adapter import ChronosAdapter
from forecasting.core.schema import ForecastInput, assert_forecast_result


def _ohlcv(n: int = 64) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=n, freq="B", tz="UTC")
    close = pd.Series(np.linspace(100, 120, n), dtype=float)
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


class _MockPipeline:
    def predict(self, context, prediction_length, num_samples=20):
        # Shape (1, num_samples, horizon)
        base = float(context[-1]) if hasattr(context, "__getitem__") else 100.0
        samples = np.stack(
            [
                np.linspace(base, base * (1 + 0.01 * s), prediction_length)
                for s in range(num_samples)
            ],
            axis=0,
        )
        return np.expand_dims(samples, 0)


def test_chronos_adapter_mock_predict():
    adapter = ChronosAdapter(pipeline=_MockPipeline())
    inp = ForecastInput(ticker="SPY", ohlcv=_ohlcv(), horizon=8)
    assert adapter.supports(inp) is True
    result = adapter.predict(inp)
    assert_forecast_result(result, horizon=8)
    assert result.model_name == "chronos"
    assert result.quantiles is not None
    assert 0.1 in result.quantiles
    assert "close" in result.predicted.columns


def test_chronos_real_optional():
    pytest.importorskip("chronos")
    adapter = ChronosAdapter()
    inp = ForecastInput(ticker="SPY", ohlcv=_ohlcv(128), horizon=5)
    if not adapter.supports(inp):
        pytest.skip("unsupported input")
    # Do not download in CI by default — only if CHRONOS_LIVE=1
    import os

    if os.environ.get("CHRONOS_LIVE") != "1":
        pytest.skip("set CHRONOS_LIVE=1 to run live Chronos download")
    result = adapter.predict(inp)
    assert_forecast_result(result, horizon=5)
