"""Event-driven backtest engine.

Event sequence for each bar ``T`` (index ``i``)
----------------------------------------------

1. **Market data becomes available.** The bar's OHLCV is known. The engine
   still must not pass bars after ``T`` into the predictor.
2. **Orders created on earlier bars fill.** Pending orders with
   ``created_bar_index + delay_bars <= i`` execute at **this bar's open**
   (never this bar's close, never the originating bar's close).
3. **Portfolio is marked to market** at this bar's close.
4. **Historical context** is ``data.get_history(T)``: timestamps ``<= T``.
5. **Kronos (or a stub predictor) forecasts** from that context only.
6. **Strategy emits BUY / SELL / HOLD.**
7. **Risk manager** may reject the signal or size an order.
8. **Order is queued.** It is not eligible until a later bar.

Same-bar close execution is impossible under this loop: a fill always uses a
bar strictly after the order's creation timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from kronos_backtest.config import BacktestConfig
from kronos_backtest.costs import TransactionCostModel
from kronos_backtest.data.loader import MarketData
from kronos_backtest.data.validator import timestamps_of, to_timestamp
from kronos_backtest.exceptions import LookAheadBiasError
from kronos_backtest.execution import ExecutionEngine, Fill
from kronos_backtest.portfolio import Portfolio
from kronos_backtest.predictor import FineTuner, Predictor, PretrainedFineTuner
from kronos_backtest.risk import RiskManager
from kronos_backtest.strategy import ExpectedReturnStrategy, PositionSizer, Strategy
from kronos_backtest.types import Bar, Signal
from kronos_backtest.walk_forward import WalkForwardEngine, WalkForwardFold


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    fills: list[Fill]
    signals: list[Signal]
    portfolio: Portfolio
    config: BacktestConfig
    metadata: dict[str, Any] = field(default_factory=dict)
    fold_id: int | None = None

    @property
    def final_equity(self) -> float:
        if self.equity_curve.empty:
            return self.portfolio.equity()
        return float(self.equity_curve["equity"].iloc[-1])


def _reproducibility(config: BacktestConfig, data: MarketData) -> dict[str, Any]:
    commit = None
    try:
        import subprocess

        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=".",
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {
        "dataset_version": data.dataset_version or config.dataset_version,
        "kronos_model_version": {
            "mode": config.model.mode,
            "model_id": config.model.model_id,
            "tokenizer_id": config.model.tokenizer_id,
        },
        "model_configuration": config.model.__dict__,
        "strategy_configuration": config.strategy.__dict__,
        "risk_configuration": config.risk.__dict__,
        "execution_configuration": config.execution.__dict__,
        "cost_configuration": {
            "costs": config.costs.__dict__,
            "slippage": config.slippage.__dict__,
            "spread": config.spread.__dict__,
        },
        "random_seed": config.seed,
        "git_commit": commit,
        "initial_capital": config.initial_capital,
    }


class BacktestEngine:
    def __init__(
        self,
        data: MarketData,
        predictor: Predictor,
        config: BacktestConfig | None = None,
        *,
        strategy: Strategy | None = None,
        fine_tuner: FineTuner | None = None,
        on_bar: Callable[[Bar, Portfolio], None] | None = None,
    ) -> None:
        self.data = data
        self.predictor = predictor
        self.config = config or BacktestConfig(symbol=data.default_symbol)
        self.strategy = strategy or ExpectedReturnStrategy.from_config(self.config)
        self.fine_tuner = fine_tuner or PretrainedFineTuner(predictor)
        self.on_bar = on_bar

    def run(self, *, symbol: str | None = None) -> BacktestResult:
        symbol = symbol or self.data.default_symbol or self.config.symbol
        if self.config.walk_forward.enabled:
            combined = self.run_walk_forward(symbol=symbol)
            return combined
        return self._run_window(self.data.bars(symbol), self.predictor, symbol=symbol)

    def run_walk_forward(self, *, symbol: str | None = None) -> BacktestResult:
        symbol = symbol or self.data.default_symbol
        index = self.data.index(symbol)
        folds = WalkForwardEngine(self.config.walk_forward).folds(index)
        results = [self.run_fold(fold, symbol=symbol) for fold in folds]
        return combine_results(results, self.config)

    def run_fold(self, fold: WalkForwardFold, *, symbol: str | None = None) -> BacktestResult:
        symbol = symbol or self.data.default_symbol
        train = self.data.slice_by_timestamps(fold.train_index, symbol=symbol)
        test = self.data.slice_by_timestamps(fold.test_index, symbol=symbol)
        fold.validate(train, test, embargo_bars=self.config.walk_forward.embargo_bars)
        predictor = self.fine_tuner.fit(train, fold.train_end, fold.test_start)
        bars = [self.data.get_bar(stamp, symbol) for stamp in fold.test_index]
        result = self._run_window(bars, predictor, symbol=symbol)
        result.fold_id = fold.fold_id
        result.metadata["fold"] = {
            "fold_id": fold.fold_id,
            "train_start": str(fold.train_start),
            "train_end": str(fold.train_end),
            "test_start": str(fold.test_start),
            "test_end": str(fold.test_end),
            "mode": fold.mode,
        }
        return result

    def _run_window(
        self,
        bars: list[Bar],
        predictor: Predictor,
        *,
        symbol: str,
    ) -> BacktestResult:
        portfolio = Portfolio(self.config.initial_capital, allow_short=self.config.risk.allow_short)
        execution = ExecutionEngine(
            TransactionCostModel.from_config(self.config),
            self.config.execution,
        )
        risk = RiskManager(self.config.risk, PositionSizer(self.config.position_sizing))
        fills: list[Fill] = []
        signals: list[Signal] = []
        equity_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []
        seed_everything(self.config.seed)

        for index, bar in enumerate(bars):
            new_fills = execution.process_orders(bar, index)
            for fill in new_fills:
                if fill.created_at is not None and fill.timestamp <= fill.created_at:
                    raise LookAheadBiasError(
                        f"Fill at {fill.timestamp} used data from order created at {fill.created_at}"
                    )
                if fill.reference_price != bar.open:
                    raise LookAheadBiasError("Fill reference is not the execution bar open")
                position = portfolio.apply_fill(fill)
                fills.append(fill)
                audit_rows.append(
                    fill.as_audit_row(position_after=position.quantity, equity=portfolio.equity())
                )

            equity = portfolio.mark_to_market(bar)
            risk.observe_equity(bar.timestamp, equity)
            context = self.data.get_history(bar.timestamp, symbol=symbol, lookback=self.config.model.lookback)
            if timestamps_of(context).max() > to_timestamp(bar.timestamp):
                raise LookAheadBiasError("Context leaked future bars into the predictor")
            prediction = predictor.predict(context, bar.timestamp)
            signal = self.strategy.generate_signal(prediction, bar, portfolio)
            signals.append(signal)
            decision = risk.validate(signal, portfolio, bar)
            if decision.order is not None:
                decision.order.created_at = bar.timestamp
                decision.order.created_bar_index = index
                execution.submit(decision.order)
            if self.on_bar:
                self.on_bar(bar, portfolio)
            snapshot = portfolio.snapshot(bar.timestamp)
            snapshot["close"] = bar.close
            snapshot["signal"] = signal.action.value
            equity_rows.append(snapshot)

        trades = pd.DataFrame(audit_rows)
        equity_curve = pd.DataFrame(equity_rows)
        if not equity_curve.empty:
            equity_curve["timestamp"] = pd.to_datetime(equity_curve["timestamp"])
        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            fills=fills,
            signals=signals,
            portfolio=portfolio,
            config=self.config,
            metadata=_reproducibility(self.config, self.data),
        )


def seed_everything(seed: int) -> None:
    import random

    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def combine_results(results: list[BacktestResult], config: BacktestConfig) -> BacktestResult:
    if not results:
        raise LookAheadBiasError("No walk-forward results to combine")
    capital = config.initial_capital
    equity_parts: list[pd.DataFrame] = []
    for item in results:
        fold_eq = item.equity_curve.copy()
        if fold_eq.empty:
            continue
        start = float(fold_eq["equity"].iloc[0]) or config.initial_capital
        scale = capital / start
        fold_eq["equity"] = fold_eq["equity"] * scale
        fold_eq["cash"] = fold_eq["cash"] * scale
        fold_eq["fold_id"] = item.fold_id
        capital = float(fold_eq["equity"].iloc[-1])
        equity_parts.append(fold_eq)
    equity = pd.concat(equity_parts, ignore_index=True) if equity_parts else pd.DataFrame()
    trade_parts = [item.trades.assign(fold_id=item.fold_id) for item in results if not item.trades.empty]
    trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    last = results[-1]
    metadata = dict(last.metadata)
    metadata["folds"] = [item.metadata.get("fold") for item in results]
    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        fills=[fill for item in results for fill in item.fills],
        signals=[signal for item in results for signal in item.signals],
        portfolio=last.portfolio,
        config=config,
        metadata=metadata,
    )
