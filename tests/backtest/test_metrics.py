from __future__ import annotations

from pathlib import Path

from kronos_backtest.config import BacktestConfig
from kronos_backtest.evaluation.metrics import compute_metrics
import pandas as pd


def test_yaml_round_trip() -> None:
    config = BacktestConfig.from_yaml(Path("configs/backtest.yaml"))
    assert config.execution.delay_bars == 1
    assert config.slippage.rate == 0.0005
    assert config.walk_forward.type == "expanding"
    assert config.risk.max_daily_loss_pct == 0.02
    assert len(config.scenarios) == 4


def test_metrics_include_required_fields() -> None:
    equity = pd.DataFrame(
        {
            "timestamp": pd.bdate_range("2020-01-01", periods=20),
            "equity": [100_000 * (1.001 ** i) for i in range(20)],
        }
    )
    trades = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-10")],
            "side": ["BUY", "SELL"],
            "quantity": [10, 10],
            "fill_price": [100, 110],
            "commission": [0.1, 0.1],
            "exchange_fees": [0.05, 0.05],
            "regulatory_fees": [0.0, 0.0],
            "slippage": [0.2, 0.2],
            "spread": [0.1, 0.1],
            "total_cost": [0.45, 0.45],
            "gross_value": [1000, 1100],
        }
    )
    metrics = compute_metrics(equity, trades, initial_capital=100_000)
    required = {
        "total_return",
        "cagr",
        "annual_return",
        "monthly_return",
        "volatility",
        "max_drawdown",
        "sharpe",
        "sortino",
        "calmar",
        "number_of_trades",
        "win_rate",
        "average_win",
        "average_loss",
        "profit_factor",
        "average_holding_period",
        "turnover",
        "total_commission",
        "total_fees",
        "total_slippage",
        "total_spread_cost",
        "total_transaction_costs",
    }
    assert required.issubset(metrics)
    assert metrics["number_of_trades"] == 2
    assert metrics["total_return"] > 0
