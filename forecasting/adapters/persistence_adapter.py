"""Naive persistence baseline (no torch). Useful for smoke tests and ensembles."""

from __future__ import annotations

import time

import pandas as pd

from forecasting.core.base import ForecastModel
from forecasting.core.schema import ForecastInput, ForecastResult


class PersistenceAdapter(ForecastModel):
    """Forecast = last close repeated for ``horizon`` bars."""

    name = "persistence"

    def __init__(self, **_kwargs) -> None:
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def supports(self, inp: ForecastInput) -> bool:
        return inp.horizon >= 1 and "close" in inp.ohlcv.columns and len(inp.ohlcv) >= 1

    def predict(self, inp: ForecastInput) -> ForecastResult:
        if not self.supports(inp):
            raise ValueError("PersistenceAdapter does not support this input")
        if not self._loaded:
            self.load()
        start = time.perf_counter()
        last = float(inp.ohlcv["close"].iloc[-1])
        predicted = pd.DataFrame({"close": [last] * inp.horizon})
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=predicted,
            latency_ms=(time.perf_counter() - start) * 1000.0,
            meta={"checkpoint": "persistence-v1", "series": "close"},
        )
