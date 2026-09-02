# Feature engine

Deterministic feature builders live under `ml/features/`.

## MVP-1 (implemented)

Technical features from daily OHLCV:

- Trend: SMA 10/20/50/100/200, EMA 10/20/50/200
- Momentum: RSI, MACD (+ signal/histogram), ROC, momentum
- Volatility: ATR, Bollinger bands/width/%B, rolling volatility
- Volume: SMA, ratio, acceleration, OBV, price-volume correlation
- Structure: distances from SMAs, breakouts, drawdown, rolling returns

`build_feature_snapshot(ticker, ohlcv, as_of=...)` truncates bars to `as_of`
before computation (`feature_version` currently `1.0.0`).

## Later MVPs

- SEC flow features (`ml/features/sec/`) — MVP-3
- Fundamentals (`ml/features/fundamentals/`) — MVP-4

Indicators are **features**, never hard-coded BUY/SELL rules.
