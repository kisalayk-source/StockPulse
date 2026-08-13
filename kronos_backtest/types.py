"""Shared value objects for the backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


PRICE_COLUMNS = ("open", "high", "low", "close")
VOLUME_COLUMNS = ("volume", "amount", "vol", "amt")
RETURN_COLUMNS = ("returns", "return", "log_return", "pct_change", "label", "y", "target")
CORPORATE_ACTION_COLUMNS = (
    "dividend",
    "dividends",
    "split",
    "split_factor",
    "adj_factor",
    "adjustment",
    "corporate_action",
)
FUTURE_SENSITIVE_COLUMNS = (
    PRICE_COLUMNS + VOLUME_COLUMNS + RETURN_COLUMNS + CORPORATE_ACTION_COLUMNS
)


@dataclass(frozen=True)
class Bar:
    timestamp: pd.Timestamp
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float = 0.0
    bid: float | None = None
    ask: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def mid(self) -> float:
        if self.bid is not None and self.ask is not None and self.ask >= self.bid:
            return (self.bid + self.ask) / 2.0
        return self.open

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
        }
        if self.bid is not None:
            payload["bid"] = self.bid
        if self.ask is not None:
            payload["ask"] = self.ask
        payload.update(self.extras)
        return payload


@dataclass(frozen=True)
class Prediction:
    timestamp: pd.Timestamp
    symbol: str
    expected_return: float
    predicted_close: float | None = None
    confidence: float = 1.0
    horizon_bars: int = 1
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Signal:
    timestamp: pd.Timestamp
    symbol: str
    action: SignalAction
    expected_return: float
    edge: float
    confidence: float = 1.0
    estimated_cost: float = 0.0
    reason: str = ""
