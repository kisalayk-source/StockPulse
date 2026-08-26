"""Eval metrics + walk-forward backtest tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from forecasting.core.base import ForecastModel
from forecasting.core.schema import ForecastInput, ForecastResult
from forecasting.data.loader import load_ohlcv_csv
from forecasting.eval.backtest import ForecastCache, walk_forward_backtest
from forecasting.eval.metrics import directional_accuracy, mae, path_metrics, rank_ic

FIXTURE = Path(__file__).parent / "fixtures" / "sample_ohlcv.csv"


class PersistenceModel(ForecastModel):
    name = "persist"

    def load(self) -> None:
        return None

    def supports(self, inp: ForecastInput) -> bool:
        return len(inp.ohlcv) >= 8 and inp.horizon >= 1

    def predict(self, inp: ForecastInput) -> ForecastResult:
        last = float(inp.ohlcv["close"].iloc[-1])
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=pd.DataFrame({"close": [last] * inp.horizon}),
            meta={"checkpoint": "persist-v1"},
        )


class DriftModel(ForecastModel):
    name = "drift"

    def load(self) -> None:
        return None

    def supports(self, inp: ForecastInput) -> bool:
        return len(inp.ohlcv) >= 8 and inp.horizon >= 1

    def predict(self, inp: ForecastInput) -> ForecastResult:
        last = float(inp.ohlcv["close"].iloc[-1])
        ret = float(inp.ohlcv["close"].pct_change().tail(10).mean() or 0.0)
        path = [last * ((1 + ret) ** (i + 1)) for i in range(inp.horizon)]
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=pd.DataFrame({"close": path}),
            meta={"checkpoint": "drift-v1"},
        )


def test_metrics_basic():
    pred = [1.0, 2.0, 3.0]
    act = [1.1, 1.9, 3.2]
    assert mae(pred, act) < 0.2
    assert directional_accuracy(pred, act) == 1.0
    assert rank_ic([3, 1, 2], [3, 1, 2]) == 1.0
    m = path_metrics(pred, act, last_close=1.0)
    assert "horizon_dir_hit" in m


def test_walk_forward_backtest(tmp_path: Path):
    ohlcv = load_ohlcv_csv(FIXTURE, ticker="TEST")
    cache = ForecastCache(tmp_path / "cache")
    report = walk_forward_backtest(
        ohlcv,
        [PersistenceModel(), DriftModel()],
        ticker="TEST",
        horizon=3,
        context_len=32,
        step=10,
        weights={"persist": 1.0, "drift": 1.0},
        strategy="weighted_average",
        cache=cache,
    )
    assert "summary" in report
    assert "persist" in report["summary"]
    assert "drift" in report["summary"]
    assert "ensemble" in report["summary"]
    assert report["summary"]["persist"]["folds"] >= 1
    # Cache should have written files
    assert any(tmp_path.joinpath("cache").iterdir())


def test_inverse_error_strategy(tmp_path: Path):
    ohlcv = load_ohlcv_csv(FIXTURE, ticker="TEST")
    report = walk_forward_backtest(
        ohlcv,
        [PersistenceModel(), DriftModel()],
        ticker="TEST",
        horizon=2,
        context_len=40,
        step=15,
        strategy="inverse_error",
        cache=ForecastCache(tmp_path / "cache2"),
    )
    assert "ensemble" in report["summary"]
