"""KronosAdapter conformance with a mock predictor (no weight download)."""

from __future__ import annotations

import pandas as pd
import pytest

from forecasting.adapters.kronos_adapter import KronosAdapter
from forecasting.core.schema import ForecastInput, assert_forecast_result


def _ohlcv(n: int = 64) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=n, freq="B", tz="UTC")
    close = pd.Series(range(100, 100 + n), dtype=float)
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


class _MockPredictor:
    def predict(self, df, x_timestamp, y_timestamp, pred_len, **kwargs):
        last = float(df["close"].iloc[-1])
        return pd.DataFrame(
            {
                "open": [last] * pred_len,
                "high": [last + 1] * pred_len,
                "low": [last - 1] * pred_len,
                "close": [last * (1 + 0.001 * (i + 1)) for i in range(pred_len)],
                "volume": [0.0] * pred_len,
                "amount": [0.0] * pred_len,
            }
        )


def test_kronos_adapter_mock_predict():
    adapter = KronosAdapter(size="small", predictor=_MockPredictor(), sample_count=1)
    inp = ForecastInput(ticker="SPY", ohlcv=_ohlcv(), horizon=5, timeframe="1Day")
    assert adapter.supports(inp) is True
    result = adapter.predict(inp)
    assert_forecast_result(result, horizon=5)
    assert result.model_name == "kronos"
    assert result.meta["checkpoint"]
    assert result.latency_ms >= 0


def test_kronos_supports_rejects_oversized_context():
    adapter = KronosAdapter(size="small", predictor=_MockPredictor(), max_context=512)
    inp = ForecastInput(
        ticker="SPY",
        ohlcv=_ohlcv(600),
        horizon=5,
        context_len=600,
        timeframe="1Day",
    )
    assert adapter.supports(inp) is False
    with pytest.raises(ValueError):
        adapter.predict(inp)


def test_kronos_supports_does_not_truncate():
    adapter = KronosAdapter(size="small", predictor=_MockPredictor())
    frame = _ohlcv(600)
    before = len(frame)
    inp = ForecastInput(ticker="SPY", ohlcv=frame, horizon=3, context_len=600)
    assert adapter.supports(inp) is False
    assert len(frame) == before


def test_kronos_predict_caps_context_to_available_bars():
    adapter = KronosAdapter(size="small", predictor=_MockPredictor())
    frame = _ohlcv(40)
    inp = ForecastInput(
        ticker="SPY",
        ohlcv=frame,
        horizon=5,
        context_len=256,
        timeframe="1Day",
    )
    assert adapter.supports(inp) is True
    result = adapter.predict(inp)
    assert result.meta["context_used"] == 40
    assert_forecast_result(result, horizon=5)
