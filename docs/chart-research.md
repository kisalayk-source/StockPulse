# Chart research overlays and strategy engines

Research-only tools on the Market **Price & prediction** chart. They never place
orders. Path forecasts and hybrid model stance remain separate — see
[how-forecast-works.md](./how-forecast-works.md).

## Chart overlays

Client-side indicators computed from historical candles in
`frontend/src/indicators.ts`. Toggle chips on the chart card (multi-select):

| Overlay | What it draws |
|---------|----------------|
| **SMA 20 / 50** | Simple moving averages on the price pane (default on) |
| **EMA 12 / 26** | Exponential moving averages on the price pane |
| **Bollinger** | 20-period middle band ± 2σ (upper / mid / lower) |
| **RSI 14** | Relative strength on a separate pane below price |
| **MACD** | MACD line, signal (9), and histogram on a separate pane |
| **Engulfing** | Bullish / bearish engulfing arrows on the candle series (`BULL ENG` / `BEAR ENG`) |

These windows intentionally match the hybrid feature engine where overlapping
(SMA/EMA/RSI/MACD/Bollinger/engulfing). Overlay math is for **display**; stance
training uses the server-side feature matrix under `ml/features/`
(`feature_version` `1.2.0`).

## Strategy engines

Selectable next to **Kronos** / **Forecast** on the chart. Strategy modes replace
the path forecast API call for that view and draw enter/exit markers on history
instead of a projected close path.

| Engine | Code | Rules (closing bar only) |
|--------|------|---------------------------|
| **Chopper** | `frontend/src/chopper.ts` | SMA 10 above SMA 20 and rising vs 5 bars ago → enter; condition ends → exit |
| **MA Cross** | `frontend/src/strategies.ts` | EMA 12 crosses above EMA 26 → enter; crosses below → exit |
| **BB Revert** | `frontend/src/strategies.ts` | Close crosses below lower Bollinger → enter; crosses back above mid → exit |

Shared wiring: `frontend/src/strategies.ts` (`calculateStrategy`,
`calculateStrategyOnForecast`). Markers and average lines render through
`MarketChart.tsx`. The strategy summary panel under the chart explains the
active rules.

When **Kronos** or **Forecast** is selected, an optional projected Chopper
overlay can still appear on the forecast path (hover to reveal SMA 10/20).

## What these are not

- Not broker orders and not trading-agent strategies
- Not substitutes for hybrid BUY/HOLD/SELL probability
- Not guaranteed edge — research visualization only

## Related

- [how-forecast-works.md](./how-forecast-works.md) — everyday chart path vs stance
- [feature-engine.md](./feature-engine.md) — server-side pattern features for stance
- [frontend/README.md](../frontend/README.md) — UI layout
