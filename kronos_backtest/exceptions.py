"""Errors raised by the production backtesting engine."""

from __future__ import annotations


class KronosBacktestError(Exception):
    """Base error for the backtesting engine."""


class LookAheadBiasError(KronosBacktestError):
    """Raised when data strictly after the current timestamp is observed.

    This is a hard failure. The engine must never continue after detecting
    future OHLC, volume, returns, indicators, labels, corporate actions, or
    training/test overlap.
    """


class ExecutionError(KronosBacktestError):
    """Raised when an order cannot be filled under the configured model."""


class ConfigurationError(KronosBacktestError):
    """Raised when backtest configuration is invalid."""


class InsufficientHistoryError(KronosBacktestError):
    """Raised when a predictor is asked for a forecast without enough history."""
