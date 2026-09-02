"""Market regime detection scaffold (MVP-2+)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def classify_market_regime(ohlcv: pd.DataFrame, *, market: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lightweight local regime from price trend/vol; market breadth lands later."""
    _ = market
    if ohlcv.empty or len(ohlcv) < 20:
        return {"regime": "UNKNOWN"}
    close = ohlcv["close"]
    ret = close.pct_change().dropna()
    vol = float(ret.tail(20).std()) if len(ret) >= 20 else float("nan")
    trend = float(close.iloc[-1] / close.iloc[-20] - 1.0)
    if vol == vol and vol > 0.025:
        regime = "HIGH_VOLATILITY"
    elif vol == vol and vol < 0.008:
        regime = "LOW_VOLATILITY"
    elif trend > 0.03:
        regime = "BULL"
    elif trend < -0.03:
        regime = "BEAR"
    else:
        regime = "SIDEWAYS"
    return {"regime": regime, "trend_20d": trend, "volatility_20d": vol}
