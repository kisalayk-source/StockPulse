from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from kronos_backtest.config import (
    BacktestConfig,
    CostConfig,
    ExecutionConfig,
    PositionSizingConfig,
    RiskConfig,
    SlippageConfig,
    SpreadConfig,
    StrategyConfig,
    WalkForwardConfig,
)
from kronos_backtest.data.loader import MarketData
from kronos_backtest.engine import BacktestEngine
from kronos_backtest.evaluation.metrics import compute_metrics
from kronos_backtest.predictor import ScriptedPredictor
from kronos_backtest.runner import run_full
from tests.backtest.helpers import ohlcv_frame


def _config(**kwargs) -> BacktestConfig:
    defaults = dict(
        initial_capital=10_000.0,
        symbol="TEST",
        seed=7,
        execution=ExecutionConfig(delay_bars=1),
        slippage=SlippageConfig(enabled=True, rate=0.0005),
        spread=SpreadConfig(enabled=True, rate=0.0005),
        costs=CostConfig(commission_rate=0.0001, exchange_fee_rate=0.00005, regulatory_fee_rate=0.0),
        walk_forward=WalkForwardConfig(enabled=False),
        position_sizing=PositionSizingConfig(max_position_pct=0.10, confidence_scaling=False),
        risk=RiskConfig(max_position_pct=0.10, max_total_exposure_pct=1.0, max_leverage=1.0),
        strategy=StrategyConfig(minimum_edge=0.002),
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


def test_deterministic_pipeline_final_equity() -> None:
    frame = ohlcv_frame(
        [
            ("2020-01-01", 100, 100),
            ("2020-01-02", 102, 102.4),
            ("2020-01-03", 105, 105),
            ("2020-01-04", 103, 103),
            ("2020-01-05", 108, 108.5),
        ]
    )
    stamps = pd.to_datetime(frame["timestamp"])
    predictor = ScriptedPredictor(
        {
            stamps.iloc[0]: 0.05,
            stamps.iloc[1]: 0.0,
            stamps.iloc[2]: 0.0,
            stamps.iloc[3]: -0.05,
            stamps.iloc[4]: 0.0,
        },
        symbol="TEST",
    )
    engine = BacktestEngine(MarketData(frame, default_symbol="TEST"), predictor, _config())
    result = engine.run()

    assert [signal.action.value for signal in result.signals] == ["BUY", "HOLD", "HOLD", "SELL", "HOLD"]
    assert len(result.fills) == 2
    buy, sell = result.fills
    assert buy.side.value == "BUY"
    assert sell.side.value == "SELL"
    assert buy.timestamp == pd.Timestamp("2020-01-02")
    assert sell.timestamp == pd.Timestamp("2020-01-05")
    assert buy.reference_price == 102
    assert sell.reference_price == 108
    assert buy.fill_price != 100
    assert buy.fill_price != 102.4

    after_spread_buy = 102 * (1 + 0.0005 / 2)
    fill_buy = after_spread_buy * (1 + 0.0005)
    gross_buy = fill_buy * 10
    cash_out = gross_buy + gross_buy * 0.0001 + gross_buy * 0.00005

    after_spread_sell = 108 * (1 - 0.0005 / 2)
    fill_sell = after_spread_sell * (1 - 0.0005)
    gross_sell = fill_sell * 10
    cash_in = gross_sell - gross_sell * 0.0001 - gross_sell * 0.00005
    expected_equity = 10_000 - cash_out + cash_in

    assert buy.quantity == pytest.approx(10)
    assert sell.quantity == pytest.approx(10)
    assert buy.fill_price == pytest.approx(fill_buy)
    assert sell.fill_price == pytest.approx(fill_sell)
    assert result.final_equity == pytest.approx(expected_equity, rel=1e-12)
    assert result.final_equity == pytest.approx(10058.110014210625, rel=1e-12)
    assert result.portfolio.cash == pytest.approx(expected_equity)
    assert result.portfolio.position("TEST").quantity == 0
    assert result.portfolio.total_commission > 0
    assert result.portfolio.total_slippage_cost > 0
    assert result.portfolio.total_spread_cost > 0

    metrics = compute_metrics(
        result.equity_curve,
        result.trades,
        initial_capital=10_000,
        portfolio=result.portfolio,
    )
    assert metrics["sharpe"] == metrics["sharpe"]
    assert metrics["sortino"] == metrics["sortino"]
    assert metrics["calmar"] == metrics["calmar"]
    assert metrics["number_of_trades"] == 2


def test_same_inputs_are_reproducible() -> None:
    frame = ohlcv_frame(
        [
            ("2020-01-01", 100, 100),
            ("2020-01-02", 102, 102),
            ("2020-01-03", 101, 101),
            ("2020-01-04", 104, 104),
        ]
    )
    predictor = ScriptedPredictor({pd.Timestamp("2020-01-01"): 0.05}, default_return=0.0, symbol="TEST")
    data = MarketData(frame, default_symbol="TEST")
    first = BacktestEngine(data, predictor, _config(seed=11)).run()
    second = BacktestEngine(data, predictor, _config(seed=11)).run()
    assert first.final_equity == second.final_equity
    assert list(first.trades["fill_price"]) == list(second.trades["fill_price"])


def test_full_run_writes_artifacts(tmp_path: Path) -> None:
    frame = ohlcv_frame(
        [
            ("2020-01-01", 100, 100),
            ("2020-01-02", 102, 102),
            ("2020-01-03", 105, 105),
            ("2020-01-04", 103, 103),
            ("2020-01-05", 108, 108),
            ("2020-01-06", 107, 107),
            ("2020-01-07", 109, 109),
            ("2020-01-08", 111, 111),
        ]
    )
    data = MarketData(frame, default_symbol="TEST", dataset_version="test")
    predictor = ScriptedPredictor({pd.Timestamp("2020-01-01"): 0.05}, default_return=0.0, symbol="TEST")
    payload = run_full(data, predictor, _config(), tmp_path)
    for name in (
        "summary.json",
        "metrics.json",
        "trades.csv",
        "equity_curve.csv",
        "daily_returns.csv",
        "drawdown.csv",
        "report.html",
    ):
        assert (tmp_path / name).exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert "buy_and_hold" in summary["benchmarks"]
    assert "momentum" in summary["benchmarks"]
    assert "moving_average" in summary["benchmarks"]
    assert set(summary["stress"]) == {"optimistic", "normal", "conservative", "severe"}
    assert summary["stress"]["optimistic"]["final_equity"] >= summary["stress"]["severe"]["final_equity"]
    assert payload["metrics"]["total_transaction_costs"] > 0
    assert "random_seed" in summary["reproducibility"]
