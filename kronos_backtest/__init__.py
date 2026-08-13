"""Production-grade historical backtesting engine for Kronos.

This package is the recommended backtester. The scripts under ``examples/``
and ``finetune/qlib_test.py`` remain as educational demos.
"""

from kronos_backtest.config import BacktestConfig
from kronos_backtest.engine import BacktestEngine, BacktestResult
from kronos_backtest.exceptions import LookAheadBiasError
from kronos_backtest.predictor import ConstantPredictor, KronosBacktestPredictor, ScriptedPredictor

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "LookAheadBiasError",
    "ConstantPredictor",
    "KronosBacktestPredictor",
    "ScriptedPredictor",
]
