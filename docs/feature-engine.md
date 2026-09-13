# Feature engine

Deterministic feature builders live under `ml/features/`.

Plain-language MVP overview: [mvp-roadmap.md](./mvp-roadmap.md).

## MVP-1 (implemented)

Technical features from daily OHLCV:

- Trend: SMA 10/20/50/100/200, EMA 10/20/50/200
- Momentum: RSI, MACD (+ signal/histogram), ROC, momentum
- Volatility: ATR, Bollinger bands/width/%B, rolling volatility
- Volume: SMA, ratio, acceleration, OBV, price-volume correlation
- Structure: distances from SMAs, breakouts, drawdown, rolling returns

`build_feature_snapshot(ticker, ohlcv, as_of=...)` truncates bars to `as_of`
before computation (`feature_version` currently `1.0.0`).

## MVP-3 (implemented) — SEC flow

Point-in-time SEC features under `ml/features/sec/`:

- Institutional (13F): counts, net polarity, `inst_flow_score`
- Insider (Form 4): discretionary buy/sell counts/values, cluster flags, `insider_flow_score`
- Ownership (13D/13G): increase/decrease counts, max ownership pct, `ownership_flow_score`

Builders accept normalized event **dicts** (from `SecService.load_normalized_events`);
only events with `filing_date` / `published_at` `<= as_of` are used. Pass
`sec_events=` into `build_feature_snapshot` (or a pre-merged `sec=` dict).

## MVP-4 (implemented) — Fundamentals

Finnhub metric passthrough under `ml/features/fundamentals/`:

- Valuation: `pe_ratio`, `market_cap`, `dividend_yield`, `eps`
- Growth: `revenue_growth`, `eps_growth`
- Profitability: `roic`, `fcf_margin`
- Health: `debt_to_equity`

Pass `fundamentals_metrics=` from `FinnhubService.extended_fundamentals` (or a
pre-merged `fundamentals=` dict). Metrics are treated as already as-of; there is
no separate historical restatement store.

Config toggles: `features.sec` / `features.fundamentals` in `ml/config/prediction.yaml`.
Tree models still train/predict on technical features only; SEC/fundamentals fill
`FeatureSnapshot` buckets and explanation scores.

Indicators are **features**, never hard-coded BUY/SELL rules.
