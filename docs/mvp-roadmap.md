# StockPulse prediction roadmap (plain language)

A non-technical guide to what each “MVP” built for StockPulse’s **model stance**
(BUY / HOLD / SELL) and how that relates to the chart path and the trading agent.

**Not investment advice.** These tools are research overlays. They never place
orders for you unless you deliberately run the autonomous agent in paper/live
mode — and even then, you control start/pause and risk limits.

For the everyday chart experience, also read
[how-forecast-works.md](./how-forecast-works.md).
For engineers, see [stock-prediction-architecture.md](./stock-prediction-architecture.md).

---

## Two research views (remember this)

| What you see | Everyday question | Who decides direction? |
|---|---|---|
| **Chart path** | “Where might the price *line* go?” | Kronos / path ensemble (sketch of a route) |
| **Model stance** | “How likely is an *up* move over the next few days?” | Hybrid prediction (calibrated probability → BUY/HOLD/SELL) |

They can disagree. That is normal — they answer different questions.

---

## Status at a glance

| Stage | Status | In one sentence |
|---|---|---|
| **MVP-1** | Done | Market data → technical clues → first BUY/HOLD/SELL probability |
| **MVP-2** | Done | Several models vote together; probabilities are calibrated |
| **MVP-3** | Done | SEC ownership / insider *flow* clues (as of a date, no peeking ahead) |
| **MVP-4** | Done | Company fundamentals (valuation, growth, health) from Finnhub |
| **MVP-5** | Done | Extra safety: soften or block BUY when risk looks too high |
| **MVP-6** | Done | Prove-it toolkit: fair backtests, “what if we remove this?”, explanations of which clues mattered |
| **MVP-7** | Done | Clearer plain-language explanations that only use real numbers from the model |
| **Government contracts** | Done | Public procurement clues (SAM.gov / USAspending) on Market + in the feature snapshot |
| **Agent alignment** | Done | Agent follows hybrid for BUY/SELL; chart path only helps size and targets |

---

## MVP-1 — First model stance

**What it is:** StockPulse reads recent prices and volumes, turns them into
familiar technical clues (trends, momentum, volatility, and so on), and a first
model estimates the chance the stock moves up over a chosen window (1, 5, or 20
trading days). That chance becomes a **BUY**, **HOLD**, or **SELL** (including
stronger variants when the probability is extreme).

**What you get:** A decision-style signal next to the chart, separate from the
drawn path line.

**What it is not:** Not a promise of profit, and not an automatic order.

---

## MVP-2 — Ensemble + fairer probabilities

**What it is:** More than one model can contribute (for example XGBoost,
LightGBM, and a read of the chart path turned into “chance of up”). Their views
are combined, then **calibrated** so a “70%” reading is closer to meaning “about
seven times out of ten in similar past cases,” instead of a raw score that looks
confident but is mis-scaled.

**What you get:** A more stable model stance when multiple members are enabled.

**What it is not:** Turning on every model does not guarantee better results —
settings still matter, and proof comes from later evaluation (MVP-6).

---

## MVP-3 — Ownership and insider flow (SEC)

**What it is:** Clues from public SEC filings (institutional 13F changes, Form 4
insider trades, major-holder 13D/13G events) are summarized into features for the
snapshot. Timing respects **point-in-time** rules: for a prediction “as of”
Tuesday, only filings that were already public by Tuesday count.

**What you get:** Richer context in the feature snapshot (and related research
views), without inventing filings.

**What it is not:** A copy of the separate Accumulation Score UI by itself — that
score still exists for research; MVP-3 feeds the hybrid feature store carefully.

---

## MVP-4 — Company fundamentals

**What it is:** Standard fundamental metrics (for example valuation, growth,
profitability, balance-sheet health) from Finnhub are attached to the same
feature snapshot when available.

**What you get:** Fundamentals sitting beside technical and SEC clues for
inspection and future model use.

**What it is not:** A guarantee that fundamentals alone drive the live stance —
tree models may still emphasize technicals until training is expanded further.

---

## Government contract analysis (done)

**What it is:** Public U.S. government procurement data (opportunities and awards
from SAM.gov, obligations from USAspending) mapped to a ticker and summarized into
a **government score** and an **early-signal score**. Timing respects the same
kind of **point-in-time** rule as SEC: only events already published by the
prediction date count. Scores are config-driven numbers, not LLM inventions.

**What you get:** A Government Contracts panel on Market (next to SEC Intelligence),
API routes to inspect or sync a symbol, optional on-screen alert banners when large
awards or high scores fire, and a `government` bucket in the hybrid feature
snapshot (`feature_version` 1.1.0) that tree models can train on when enabled.

**What it is not:** A promise that a contract win means the stock will rise, push
or email notifications, or a separate trading system — it plugs into the existing
StockPulse research and prediction stack.

Technical detail: [government.md](./government.md).

---

## MVP-5 — Signal risk (safety net)

**What it is:** After the models propose a stance, an independent **signal risk**
check looks at things like high volatility, deep drawdowns, and (when known)
heavy position concentration. It can **downgrade** a strong BUY to BUY, or
**veto** a BUY down to HOLD, when risk thresholds are breached.

**What you get:** Fewer aggressive BUY readings when market conditions look
unhealthy for that name.

**What it is not:** The same thing as broker pre-trade checks (order size, daily
loss limits). Those remain separate.

---

## MVP-6 — Prove it

**What it is:** Tools to test honesty before trusting the stack more:

- **Walk-forward tests** — train on earlier history, test on later history (no
  peeking)
- **Ablations** — remove a group of clues (for example momentum) and see whether
  quality changes
- **SHAP / importance** — which clues the tree models leaned on
- **Registry metrics** — saved model cards record validation scores (accuracy,
  calibration-style metrics, and related stats)

**What you get:** A way to compare setups fairly instead of eyeballing a few
lucky days.

**What it is not:** A live “always right” badge. Markets change; evaluation is
ongoing.

---

## MVP-7 — Plain explanations

**What it is:** Human-readable explanations of a stance that are allowed to
use **only** numbers and fields already produced by the quantitative engine —
no invented prices, filings, or probabilities.

A clear **template** summary is always built first. When AI summaries are
enabled for your account (and the server has OpenAI configured), StockPulse may
add a short narrated paragraph that rephrases those same figures. If AI is off
or fails, you still get the template.

**What you get:** Easier-to-read stance notes under the decision panel /
explanation endpoint, still grounded in the model output.

**What it is not:** Permission for the model to invent new stats or place trades.

---

## Agent alignment (done)

Once the hybrid ensemble is live, the **autonomous trading agent** is aligned like
this:

| Source | Agent uses it for |
|---|---|
| **Hybrid model stance** | The only BUY / HOLD / SELL decision |
| **Kronos / chart path** | Expected move, target/stop hints, and position sizing |

If hybrid prediction is unavailable, the agent stays on **HOLD** rather than
inventing a BUY/SELL from the path alone.

Paper/live agent cycles still respect your risk profile, Forecast Mode toggle,
and start/pause controls.

**Symbols:** manual **Run forecast cycle** can use any typed tickers (ad-hoc —
not saved to the risk portfolio). Scheduled auto-cycles use only the saved risk
portfolio (max 50). Details: [trading-agent.md](./trading-agent.md).

---

## What to trust (and what not to)

**Do**

- Treat path and stance as two research lenses
- Check risk score and any “risk gate” notes when a BUY looks aggressive
- Prefer paper trading while learning the agent

**Don’t**

- Assume path “bullish” means the model says BUY
- Assume a high probability removes risk
- Expect SEC, fundamentals, or government scores alone to “confirm” a trade
  without looking at the full snapshot and risk gates

---

## Where to read next

| Audience | Document |
|---|---|
| Everyday chart use | [how-forecast-works.md](./how-forecast-works.md) |
| Architecture & leakage rules | [stock-prediction-architecture.md](./stock-prediction-architecture.md) |
| Features / models / risk / eval (technical) | [feature-engine.md](./feature-engine.md), [model-engine.md](./model-engine.md), [risk-engine.md](./risk-engine.md), [backtesting.md](./backtesting.md), [model-evaluation.md](./model-evaluation.md) |
| Government contracts | [government.md](./government.md) |
| Kronos adapter | [kronos.md](./kronos.md) |
| Prediction API | [api.md](./api.md) |
| Trading agent | [trading-agent.md](./trading-agent.md) |
| Local setup | [DEVELOPMENT.md](./DEVELOPMENT.md) |
