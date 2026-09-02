# How StockPulse forecasts work

A plain-language guide for people who use StockPulse and want to understand what the Market tab is showing — without needing to know how the software is built.

**Short version:** StockPulse can draw a possible future price path on the chart and show a separate research signal (BUY / HOLD / SELL with a probability). Neither of these places a trade. You always decide and submit orders yourself.

This is **not investment advice**. Forecasts and signals are research tools. Markets can move differently than any model expects.

---

## Two different tools (not the same thing)

Think of two helpers sitting next to the chart:

| Tool | Everyday meaning | Where you see it |
|------|------------------|------------------|
| **Chart path** | “Where might the price line go next?” | The projected line on the chart, under **Price & prediction** |
| **Model stance** | “How likely does an upward move look over the next few trading days?” | The decision panel under the chart (BUY / HOLD / SELL, model P(up), model risk) |

They answer different questions. A chart path can look **bullish** while the model stance says **SELL** (or the reverse). That is normal — complementary research views, not one conflicting “order.”

---

## Step by step: what happens when you open a stock

1. **You choose a ticker** on the Market tab (for example SPY or AAPL).
2. **StockPulse loads recent prices** as candles on the chart — that is history, not a prediction.
3. **The path forecast** looks at that recent history and draws a projected path **ahead** of the last known price (what the line might do next).
4. **The hybrid engine** looks at price patterns — things like trend, momentum, volatility, and volume — and estimates a probability that the stock moves up over a chosen time window. That probability is turned into a research signal such as BUY, HOLD, or SELL using fixed rules.
5. **The decision panel** shows both: chart-path summary (target, move, bias) and model-stance summary (BUY/HOLD/SELL, P(up), risk, window), plus news and market-mood cues that can help you judge context.

Nothing in steps 3–5 sends an order to your broker.

---

## How to read the screen

### On the chart

- **Candles / history** — what already happened.
- **Forecast line** — a model’s guess for the next stretch of closes. It can bend up, down, or sideways.
- **Short vs long** (and chart interval) — controls how far ahead the path looks and how fine-grained the candles are (minutes vs days).

### In the decision panel

| Label | What it means in plain English |
|-------|--------------------------------|
| **Chart path target** | The end price the chart forecast line is pointing toward |
| **Chart path move** | How much that path implies the price might change (often shown after rough trading costs) |
| **Chart path window** | How far ahead that path is looking |
| **Chart path bias** | Simple read of the forecast line: bullish, bearish, or in between |
| **Model stance** | Separate probability call: BUY, STRONG BUY, HOLD, SELL, or STRONG SELL |
| **Model P(up)** | Estimated chance of a positive move over the model’s time window (for example ~5 trading days) |
| **Model risk** | Caution meter for the model call (higher usually means more uncertainty or stress in the inputs) |
| **Model window** | The holding window the model stance is aiming at (for example `5d` ≈ about a week of trading days, `20d` ≈ about a month) |
| **Why it may go up / down** | Headlines, public sentiment, and “market mood” cues — context for judgment, not a full causal model |

---

## Short vs long, and signal horizons

- **Short path** — nearer-term path on the chart (often using shorter candles).
- **Long path** — farther-ahead path (often daily candles).
- **Model window** — usually about **5 trading days**; longer chart setups can use about **20 trading days**. These are research windows, not promises of when something will happen.

If the chart interval or horizon feels wrong for how you think about a stock, change it and reload — the path and signal will refresh for that setting.

---

## Kronos vs Forecast (on the chart)

On the Market tab you can choose how the **path** is built:

- **Kronos** — one primary forecasting model draws the path.
- **Forecast** — several path models are combined into one overlay (an “ensemble”).

Both are still research overlays. Switching modes can change the shape of the line; it does not enable auto-trading.

---

## What these tools do well — and what they cannot do

**Useful for**

- Visualizing one possible near-term path
- Getting a structured probability and signal alongside news and ownership context
- Comparing names or horizons while you stay in paper (practice) mode

**Limits to remember**

- Every forecast is a **probability**, not a guarantee. Models can be wrong — often.
- Patterns from the past do not lock in the future.
- News, sentiment, and SEC ownership scores are **context**, not proof that a stock will rise or fall.
- A BUY or SELL label is a research classification, **not** an order and **not** personal financial advice.
- StockPulse does **not** place trades from forecasts or signals. Only you can submit an order through the ticket and review flow.

---

## Safety reminder

- Prefer **paper** mode until you are comfortable with the workflow.
- Live trading requires extra confirmation on purpose.
- Read the on-screen disclaimer: path forecasts and hybrid signals are probabilistic research outputs. They never trigger orders.

---

## Want the technical deep dive?

If you prefer architecture detail (data sources, models, and how path forecast differs from hybrid prediction in the codebase), see [stock-prediction-architecture.md](./stock-prediction-architecture.md).
