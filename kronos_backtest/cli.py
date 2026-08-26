"""Command-line entry point: python -m kronos_backtest."""

from __future__ import annotations

import argparse
from pathlib import Path

from kronos_backtest.config import BacktestConfig
from kronos_backtest.data.loader import MarketData, synthetic_ohlcv
from kronos_backtest.predictor import ConstantPredictor
from kronos_backtest.runner import build_predictor, run_full


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Production-grade Kronos historical backtester (no look-ahead, next-bar fills)."
    )
    parser.add_argument("--config", type=Path, default=Path("configs/backtest.yaml"))
    parser.add_argument("--data", type=Path, default=None, help="OHLCV CSV. Omit to run the synthetic demo.")
    parser.add_argument("--output", type=Path, default=Path("backtest_results"))
    parser.add_argument(
        "--predictor",
        choices=("kronos", "dummy"),
        default="dummy",
        help="dummy is deterministic and does not download weights.",
    )
    args = parser.parse_args(argv)

    config = BacktestConfig.from_yaml(args.config) if args.config.exists() else BacktestConfig()
    if args.data is None:
        frame = synthetic_ohlcv([100, 102, 105, 103, 108, 110, 109, 112], symbol=config.symbol)
        data = MarketData(frame, default_symbol=config.symbol, dataset_version="synthetic-demo")
    else:
        data = MarketData.from_csv(args.data, default_symbol=config.symbol)

    if args.predictor == "dummy":
        predictor = ConstantPredictor(expected_return=0.05, symbol=data.default_symbol)
    else:
        predictor = build_predictor(config)

    payload = run_full(data, predictor, config, args.output)
    metrics = payload["metrics"]
    print(f"Final equity: {metrics['final_equity']:.2f}")
    print(f"Total return: {metrics['total_return']:.4%}")
    print(f"Sharpe: {metrics['sharpe']:.4f}")
    print(f"Trades: {metrics['number_of_trades']}")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
