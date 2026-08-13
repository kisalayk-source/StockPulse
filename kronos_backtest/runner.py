"""Run a configured backtest plus benchmarks and stress scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kronos_backtest.config import BacktestConfig
from kronos_backtest.data.loader import MarketData
from kronos_backtest.engine import BacktestEngine, BacktestResult
from kronos_backtest.evaluation.benchmark import (
    BuyAndHoldStrategy,
    MomentumStrategy,
    MovingAverageStrategy,
)
from kronos_backtest.evaluation.metrics import compute_metrics
from kronos_backtest.evaluation.report import write_report
from kronos_backtest.predictor import ConstantPredictor, Predictor
from kronos_backtest.strategy.strategy import Strategy


def metrics_for(result: BacktestResult) -> dict[str, Any]:
    return compute_metrics(
        result.equity_curve,
        result.trades,
        initial_capital=result.config.initial_capital,
        portfolio=result.portfolio,
    )


def run_backtest(
    data: MarketData,
    predictor: Predictor,
    config: BacktestConfig,
    *,
    strategy: Strategy | None = None,
) -> BacktestResult:
    engine = BacktestEngine(data, predictor, config, strategy=strategy)
    return engine.run()


def run_benchmarks(
    data: MarketData,
    predictor: Predictor,
    config: BacktestConfig,
) -> dict[str, dict[str, Any]]:
    specs: list[tuple[str, Strategy]] = [
        ("buy_and_hold", BuyAndHoldStrategy()),
        ("momentum", MomentumStrategy(data)),
        ("moving_average", MovingAverageStrategy(data)),
    ]
    results: dict[str, dict[str, Any]] = {}
    for name, strategy in specs:
        result = run_backtest(data, predictor, config, strategy=strategy)
        payload = metrics_for(result)
        payload["final_equity"] = result.final_equity
        results[name] = payload
    return results


def run_stress(
    data: MarketData,
    predictor: Predictor,
    config: BacktestConfig,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for scenario in config.scenarios:
        stressed = config.with_scenario(scenario)
        result = run_backtest(data, predictor, stressed)
        payload = metrics_for(result)
        payload["final_equity"] = result.final_equity
        payload["slippage"] = scenario.slippage
        payload["transaction_cost"] = scenario.transaction_cost
        results[scenario.name] = payload
    return results


def run_full(
    data: MarketData,
    predictor: Predictor,
    config: BacktestConfig,
    output_dir: str | Path,
) -> dict[str, Any]:
    result = run_backtest(data, predictor, config)
    metrics = metrics_for(result)
    benchmarks = run_benchmarks(data, predictor, config)
    stress = run_stress(data, predictor, config)
    write_report(result, output_dir, metrics=metrics, benchmarks=benchmarks, stress=stress)
    return {
        "result": result,
        "metrics": metrics,
        "benchmarks": benchmarks,
        "stress": stress,
        "output_dir": str(output_dir),
    }


def build_predictor(config: BacktestConfig) -> Predictor:
    if config.model.mode == "pretrained" and config.model.model_id == "dummy":
        return ConstantPredictor(expected_return=0.01, symbol=config.symbol)
    from kronos_backtest.predictor import KronosBacktestPredictor

    return KronosBacktestPredictor.from_pretrained(
        tokenizer_id=config.model.tokenizer_id,
        model_id=config.model.model_id,
        device=config.model.device,
        max_context=config.model.max_context,
        lookback=config.model.lookback,
        pred_len=config.model.pred_len,
        sample_count=config.model.sample_count,
        temperature=config.model.temperature,
        top_k=config.model.top_k,
        top_p=config.model.top_p,
        symbol=config.symbol,
    )
