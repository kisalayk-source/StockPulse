# Autonomous Trading Agent

Paper/live agent that runs forecast → risk → (optional) execute cycles. Hybrid
prediction owns **BUY / HOLD / SELL**; Kronos / path forecasts supply expected
move and target/stop hints for sizing only. See
[mvp-roadmap.md](./mvp-roadmap.md#agent-alignment-done).

## Symbol sources (important)

Auto-cycles and a manual **Run forecast cycle** with an empty ticker field scan
tradable **NYSE** and **NASDAQ** stocks. Each cycle forecasts the next scored symbols and wraps to the start. Names with no hybrid signal, no price, or a forecast error are skipped and the walk continues, up to 200 attempts, until 50 scored names are found. Favorites and the risk portfolio do not
limit that scan.

| Source | Used when | Persisted? |
|--------|-----------|------------|
| **NYSE + NASDAQ listing** | Scheduled auto-cycles; manual Run when the ticker field is empty | No — next offset is stored on the last completed run |
| **Typed tickers (ad-hoc)** | Manual **Run forecast cycle** with a non-empty ticker field | No — sent only as that cycle’s `symbols` |
| **Risk portfolio (`config.universe`)** | Fallback when the exchange listing is unavailable | Yes — max **50** tickers |
| **Favorites** | Optional **Sync favorites** into the risk portfolio | Only after you sync/Add. Does not limit the exchange scan |

Default risk portfolio on first config: `SPY`, `AAPL`, `MSFT`, `NVDA`, `AMZN`.
That list is not the auto-cycle universe.

### Manual cycle (type-and-run)

1. Start the agent (paper or live) with Forecast Mode enabled.
2. Leave the ticker field empty to scan the next NYSE/NASDAQ batch, or type
   tickers (e.g. `GOOG, AMZN`) to scan only those.
3. Click **Run forecast cycle**. Typed symbols are posted to
   `POST /trading-agent/cycle` and are **not** written to `config.universe`.
   An empty field omits `symbols`, so the backend walks the exchange list.

**Add** still saves tickers into the risk portfolio. Sync favorites merges
watchlist tickers into that saved list (subject to the 50 cap). Neither list
replaces the exchange scan.

### Auto-cycles

When the agent is running, the backend scheduler calls `run_cycle` on
`cycle_interval_seconds` (default 300) with no symbol override. The cycle
takes the next 50 tradable NYSE and NASDAQ symbols. If Alpaca cannot return
the listing, the cycle falls back to the saved risk portfolio. Pause /
Emergency Stop halt auto-cycling.

## API (prefix `/api/v1`)

| Method | Path | Notes |
|--------|------|--------|
| GET/PUT | `/trading-agent/config` | Includes `universe`, `max_universe_size` (50), `last_universe_scan`, risk, intervals |
| POST | `/trading-agent/start` \| `pause` \| `resume` \| `emergency-stop` | Lifecycle |
| POST | `/trading-agent/cycle` | Body: `{ "symbols"?: string[], "execute": true }`. If `symbols` is set, it is validated (`normalize_universe`) and used for that run only. If omitted (`null`), the cycle walks the next 50 tradable NYSE and NASDAQ symbols (fallback: saved universe). Empty / invalid `symbols` → **422**. |
| GET | `/trading-agent/forecasts` | Forecasts for the **saved** universe |
| GET | `/trading-agent/candidates` \| `trade-plans` \| `orders` \| `positions` \| `events` \| `performance` | Run artifacts |
| GET | `/trading-agent/day-trades` | Session day-trades report |
| GET/PUT | `/trading-agent/daily-loss` | Daily loss limits; `POST …/daily-loss/reset` |

Auth: same as other trading routes (user JWT; broker credentials for order
routing). Live mode still requires server `ALLOW_LIVE_TRADING` and arming with
`LIVE`.

## UI

Dashboard tab **Trading Agent** (`TradingAgentPanel.tsx`):

- Risk portfolio chips (auto-cycle list) + ticker field for ad-hoc or Add
- Run button labels typed tickers when present (`Run forecast cycle (GOOG, AMZN)`)
- Universe scan table shows outcomes for the **last cycle’s** symbols (ad-hoc or saved)
- Hybrid horizon follows trading mode: day trading `1d`, long term `20d`, options and mixed `5d`. The sizing path uses that same horizon so the forecast cache can hit.
- Stops use the 10th percentile of path lows (long) or the 90th percentile of path highs (short), not the extreme of the path.
- A tree that lacks `min_train_rows` is omitted. The hybrid signal still emits when another member, including Kronos, has a probability.
- Accepted opportunities are the current session day (daily-loss timezone, default America/Los_Angeles)
- Daily trades report lists that day's fills and accepted names whose orders did not fill
- Daily loss, candidates, orders, day trades, performance

## Code map

| Area | Path |
|------|------|
| Service / `normalize_universe` | `backend/app/trading_agent/service.py` |
| API routes | `backend/app/api/trading_agent.py` |
| Scheduler | `backend/app/trading_agent/scheduler.py` |
| Forecast provider | `backend/app/trading_agent/forecast_provider.py` |
| UI | `frontend/src/TradingAgentPanel.tsx` |
| Tests | `backend/tests/test_trading_agent.py`, `frontend/src/TradingAgentPanel.test.tsx` |

## Related

- [mvp-roadmap.md](./mvp-roadmap.md#agent-alignment-done) — hybrid vs path roles
- [stock-prediction-architecture.md](./stock-prediction-architecture.md#agent-alignment) — technical alignment
- [risk-engine.md](./risk-engine.md) — signal risk (separate from agent portfolio gates)
- [api.md](./api.md) — hybrid prediction + agent endpoint summary
- [logging.md](./logging.md) — scheduler / cycle log filters
