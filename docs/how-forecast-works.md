# How StockPulse forecasts work

A plain-language guide for people who use StockPulse and want to understand what the Market tab is showing — without needing to know how the software is built.

**Short version:** StockPulse can draw a possible future **chart path** on the chart and show a separate **model stance** (BUY / HOLD / SELL with a probability). You can also turn on **indicator overlays** and **strategy engines** (Chopper, MA Cross, BB Revert) for research markers. None of these places a trade. You always decide and submit orders yourself. When path and stance disagree, that is expected — they answer different questions.

This is **not investment advice**. Forecasts and signals are research tools. Markets can move differently than any model expects.

---

## Three research layers (not the same thing)

Think of helpers sitting next to the chart:

| Tool | Everyday meaning | Where you see it |
|------|------------------|------------------|
| **Chart path** | “Where might the price line go next?” | Projected line under **Price & prediction** (Kronos or Forecast) |
| **Model stance** | “How likely does an upward move look over the next few trading days?” | Decision panel (BUY / HOLD / SELL, model P(up), model risk) |
| **Overlays & strategies** | “What do classic indicators / rule markers say on this history?” | Overlay chips + Chopper / MA Cross / BB Revert engines |

A chart path can look **bullish** while the model stance says **SELL** (or the reverse). Strategy enter/exit arrows can disagree with both. That is normal — complementary research views, not one conflicting “order.”

Technical detail for overlays and strategies: [chart-research.md](./chart-research.md).

---

## How the chart path is determined

**Question it answers:** “Where might the price line go next?”

1. StockPulse loads recent prices (candles) for the ticker.
2. Those prices are sent to a **path forecasting** model — **Kronos** by default, or **Forecast** (several path models combined).
3. The model draws a **projected close path** ahead of the last known price — the line you see on the chart.
4. **Chart path bias** (bullish / bearish / flat) is a simple read of that line: roughly, is the end of the path higher or lower than today’s last close?
5. The sentence that starts with **Chart path:** (for example “falls … then rises …”) describes turns along that same line. It is still the path forecast, not the model stance.

Think of this as a **sketch of a possible route**, not a BUY or SELL button.

---

## How the model stance is determined

**Question it answers:** “How likely does an upward move look over the next few trading days?”

1. StockPulse loads a longer stretch of **daily** prices.
2. It measures familiar market patterns (trend, momentum, volatility, volume, structure, and candle/regime **pattern features** such as SMA crosses, higher-high/higher-low, and engulfing flags). These are **inputs** to a classifier, not automatic trade rules like “RSI is low so buy.”
3. A separate **classifier model** (XGBoost, with optional LightGBM / Kronos path→P(up) in the ensemble) estimates **Model P(up)** — the chance of a positive move over a fixed window such as about 5 or 20 trading days.
4. That probability is mapped to a **Model stance** label (BUY, HOLD, SELL, and strong variants) using fixed research thresholds.
5. **Model risk** is a separate caution meter; it is not the same as broker order-risk checks in the trading ticket.

Feature set version for stance training is currently **`1.2.0`** (includes pattern features). See [feature-engine.md](./feature-engine.md).

Think of this as a **probability call for a holding window**, not a drawing of the price line.

---

## Chart overlays and strategy engines

### Overlay chips

On **Price & prediction**, toggle research indicators on the candles:

- **SMA 20 / 50**, **EMA 12 / 26**, **Bollinger** — on the price pane
- **RSI 14**, **MACD** — on panes below the price
- **Engulfing** — bullish / bearish engulfing arrows on bars

Overlays are computed in the browser from the loaded history. They do not change the path model or place orders.

### Strategy engines (Chopper, MA Cross, BB Revert)

Next to **Kronos** / **Forecast** you can pick a **strategy engine**. In that mode the chart shows rule-based enter/exit markers and the strategy’s fast/slow averages instead of calling the path-forecast API:

| Engine | Idea |
|--------|------|
| **Chopper** | SMA 10 / 20 trend regime (enter when fast is above slow and rising) |
| **MA Cross** | EMA 12 / 26 golden and death crosses |
| **BB Revert** | Mean-revert: enter below the lower Bollinger band; exit above the middle band |

When you stay on Kronos or Forecast, a projected Chopper overlay can still appear on the forecast path (SMA 10/20 on hover). Full rules: [chart-research.md](./chart-research.md).

---

## Why chart path and model stance can disagree

They are built differently on purpose. Seeing **chart path bias: bullish** next to **model stance: SELL** (or the reverse) does **not** mean the app is broken.

| | Chart path | Model stance |
|--|------------|--------------|
| **Main question** | What shape might prices take next? | What’s the chance of an up move over this window? |
| **Main output** | Future price line + bullish/bearish bias | BUY / HOLD / SELL + Model P(up) |
| **Kind of model** | Path / time-series forecast (Kronos or ensemble) | Probability classifier on price patterns |
| **Time feel** | Short or long path bars (can be minutes or days) | Fixed trading-day window (`5d` or `20d`) |

**Everyday example:** The path line can end higher overall (bullish bias) while dipping and chopping along the way, and the classifier may still judge that a clean up-move over the next week is not likely enough for a BUY — so stance stays HOLD or SELL. The opposite can happen too.

Use them as **research views**:

- Chart path — “What route is the forecast sketching?”
- Model stance — “How strong is the up-move probability for this window?”
- Overlays / strategies — “What do classic indicators and rule markers show on this history?”

Neither one places a trade. You decide.

---

## Step by step: what happens when you open a stock

1. **You choose a ticker** on the Market tab (for example SPY or AAPL).
2. **StockPulse loads recent prices** as candles on the chart — that is history, not a prediction.
3. **Optional overlays** (SMA, EMA, Bollinger, RSI, MACD, engulfing) draw on that history when toggled.
4. **The chart path** (Kronos / Forecast) looks at recent history and draws a projected path **ahead** of the last known price — or a **strategy engine** draws enter/exit markers instead of a path.
5. **The model stance engine** looks at price patterns — trend, momentum, volatility, volume, and pattern features — and estimates a probability that the stock moves up over a chosen time window. That probability becomes a research stance such as BUY, HOLD, or SELL.
6. **The decision panel** (when not in a pure strategy engine view) shows chart-path summary and model-stance summary, plus news and market-mood cues.

Nothing in steps 3–6 sends an order to your broker.

---

## How to read the screen

### On the chart

- **Candles / history** — what already happened.
- **Forecast line** — a model’s guess for the next stretch of closes (Kronos / Forecast modes).
- **Overlay lines / panes** — SMA, EMA, Bollinger, RSI, MACD when toggled.
- **Engulfing / strategy arrows** — research markers only.
- **Short vs long** (and chart interval) — how far ahead the path looks and how fine-grained the candles are.

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

Strategy engine mode replaces the path decision copy with a short panel for that strategy’s regime and enter/exit counts.

---

## Short vs long, and signal horizons

- **Short path** — nearer-term path on the chart (often using shorter candles).
- **Long path** — farther-ahead path (often daily candles).
- **Model window** — usually about **5 trading days**; longer chart setups can use about **20 trading days**. These are research windows, not promises of when something will happen.

If the chart interval or horizon feels wrong for how you think about a stock, change it and reload — the path and signal will refresh for that setting.

---

## Kronos vs Forecast vs strategy engines

On the Market tab you choose how the **main chart research mode** works:

- **Kronos** — one primary forecasting model draws the path.
- **Forecast** — several path models are combined into one overlay (an “ensemble”).
- **Chopper / MA Cross / BB Revert** — rule markers on history; no path-forecast API call in that mode.

All of these are still research overlays. Switching modes can change what you see; it does not enable auto-trading.

---

## What these tools do well — and what they cannot do

**Useful for**

- Visualizing one possible near-term path
- Getting a structured probability and signal alongside news and ownership context
- Reading classic indicators and simple strategy markers on the same chart
- Comparing names or horizons while you stay in paper (practice) mode

**Limits to remember**

- Every forecast is a **probability**, not a guarantee. Models can be wrong — often.
- Patterns from the past do not lock in the future.
- News, sentiment, SEC ownership scores, and government contract scores are
  **context**, not proof that a stock will rise or fall.
- A BUY or SELL label is a research classification, **not** an order and **not** personal financial advice.
- Indicator overlays and strategy arrows are **not** trading instructions.
- StockPulse does **not** place trades from forecasts or signals. Only you can submit an order through the ticket and review flow.

---

## Safety reminder

- Prefer **paper** mode until you are comfortable with the workflow.
- Live trading requires extra confirmation on purpose.
- Read the on-screen disclaimer: chart-path forecasts, model-stance calls, overlays, and strategy markers are probabilistic or rule-based research outputs. They never trigger orders.

---

## Favorites and AI Research

- **Favorites** — sign in, then star the active Market symbol. Saved tickers appear on the **Favorites** tab; click a row to open it on Market, or remove it from the list.
- **AI Research** — natural-language queries rank a small candidate set by **model stance** (P(up)) and **chart path bias**, with SEC accumulation as secondary context. Mentions of “favorites” or “watchlist” limit the universe to your starred tickers.

---

## Want the technical deep dive?

- **Chart overlays & strategies:** [chart-research.md](./chart-research.md)
- **MVP roadmap (plain language):** [mvp-roadmap.md](./mvp-roadmap.md) — what MVP-1…7 and agent alignment mean without code
- **Trading agent:** [trading-agent.md](./trading-agent.md) — ad-hoc cycles vs saved risk portfolio
- **Architecture:** [stock-prediction-architecture.md](./stock-prediction-architecture.md) — data sources, models, leakage rules
- **Feature engine:** [feature-engine.md](./feature-engine.md) — stance inputs including pattern features (`1.2.0`)
