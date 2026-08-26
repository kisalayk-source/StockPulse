"""Schema / ForecastModel contract tests."""

from __future__ import annotations

import time

import pandas as pd
import pytest

from forecasting.core.base import ForecastModel
from forecasting.core.schema import (
    ForecastInput,
    ForecastResult,
    assert_canonical_ohlcv,
    assert_forecast_result,
)


def _sample_ohlcv(n: int = 32) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=n, freq="B", tz="UTC")
    close = pd.Series(range(100, 100 + n), dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        },
        index=idx,
    )


class StubAdapter(ForecastModel):
    name = "stub"

    def __init__(self) -> None:
        self.loaded = False
        self.supports_calls = 0

    def load(self) -> None:
        self.loaded = True

    def supports(self, inp: ForecastInput) -> bool:
        self.supports_calls += 1
        # Guardrail: never mutate input
        before = list(inp.ohlcv.columns)
        ok = len(inp.ohlcv) >= 8 and inp.horizon >= 1
        assert list(inp.ohlcv.columns) == before
        return ok

    def predict(self, inp: ForecastInput) -> ForecastResult:
        if not self.loaded:
            self.load()
        start = time.perf_counter()
        last = float(inp.ohlcv["close"].iloc[-1])
        predicted = pd.DataFrame(
            {"close": [last * (1.0 + 0.001 * (i + 1)) for i in range(inp.horizon)]}
        )
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=predicted,
            latency_ms=(time.perf_counter() - start) * 1000.0,
            meta={"stub": True},
        )


def test_canonical_ohlcv_ok():
    frame = _sample_ohlcv()
    assert_canonical_ohlcv(frame)


def test_canonical_ohlcv_rejects_missing_columns():
    frame = _sample_ohlcv()[["close", "volume"]]
    with pytest.raises(AssertionError, match="missing columns"):
        assert_canonical_ohlcv(frame)


def test_stub_adapter_conforms():
    adapter = StubAdapter()
    inp = ForecastInput(ticker="TEST", ohlcv=_sample_ohlcv(), horizon=5)
    assert adapter.supports(inp) is True
    result = adapter.predict(inp)
    assert_forecast_result(result, horizon=5)
    assert result.model_name == "stub"
    assert result.ticker == "TEST"
    assert adapter.loaded is True


def test_supports_does_not_mutate_input():
    adapter = StubAdapter()
    frame = _sample_ohlcv(4)  # too short
    cols = list(frame.columns)
    values = frame.copy()
    inp = ForecastInput(ticker="TEST", ohlcv=frame, horizon=3)
    assert adapter.supports(inp) is False
    assert list(frame.columns) == cols
    pd.testing.assert_frame_equal(frame, values)


def test_assert_forecast_result_rejects_bad_horizon():
    result = ForecastResult(
        model_name="x",
        ticker="T",
        predicted=pd.DataFrame({"close": [1.0, 2.0]}),
    )
    with pytest.raises(AssertionError, match="horizon"):
        assert_forecast_result(result, horizon=5)
