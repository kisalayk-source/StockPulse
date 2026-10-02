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
- Patterns: SMA cross / trend align, SMA20 slope, higher-high/higher-low,
  close location in 20d range, body ratio, engulfing flags, gap return

`build_feature_snapshot(ticker, ohlcv, as_of=...)` truncates bars to `as_of`
before computation (`feature_version` currently `1.2.0`).

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

## Government contracts (implemented)

Point-in-time government features under `ml/features/government/`:

- Window counts/values: awards (7d/30d/90d), obligations, opportunities
- Scores: `government_score`, `government_early_signal_score`
- Flags: `government_new_customer`, `government_incumbent`, `government_sole_source`,
  `government_multi_year`, `government_revenue_ratio`

Builders accept normalized event **dicts** (from `GovernmentService`); only events
with `event_at <= as_of` **and** `published_at <= as_of` (when present) are used.
Pass `government_events=` into `build_feature_snapshot` (or a pre-merged
`government=` dict). See [government.md](./government.md).

Config toggles: `features.sec` / `features.fundamentals` / `features.government` in
`ml/config/prediction.yaml`. When a category flag is true, that bucket is merged into
the XGBoost/LightGBM train/predict matrix (`_merge_model_features` /
`_attach_government_features`). Disabled categories still may appear empty on the
snapshot but are not trained on.

Indicators are **features**, never hard-coded BUY/SELL rules.

## Chart UI vs stance features

The Market chart can draw overlapping indicator windows (SMA, EMA, Bollinger,
RSI, MACD, engulfing markers) in the browser for research display. That UI lives
in `frontend/src/indicators.ts` and is documented in
[chart-research.md](./chart-research.md). Stance **training and inference** use
this server-side feature matrix (`feature_version` `1.2.0`), including the
**patterns** ablation group in `ml/backtesting/ablation.py`. New pattern keys
force a new registry key so tree models retrain on cold predict / gated retrain.
