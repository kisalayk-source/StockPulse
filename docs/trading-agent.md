# Autonomous Trading Agent

Paper/live agent that runs forecast → risk → (optional) execute cycles. Hybrid
prediction owns **BUY / HOLD / SELL**; Kronos / path forecasts supply expected
move and target/stop hints for sizing only. See
[mvp-roadmap.md](./mvp-roadmap.md#agent-alignment-done).

## Symbol sources (important)

The agent is **not** limited to Kronos movers, the blue-chip scan list, or
Favorites. Any ticker matching the agent ticker pattern can be forecasted and
traded when market data and hybrid signals are available.

| Source | Used when | Persisted? |
|--------|-----------|------------|
| **Typed tickers (ad-hoc)** | Manual **Run forecast cycle** with a non-empty ticker field | No — sent only as that cycle’s `symbols` |
| **Risk portfolio (`config.universe`)** | Scheduled auto-cycles; manual Run when the ticker field is empty | Yes — max **50** tickers |
| **Favorites** | Optional **Sync favorites** into the risk portfolio | Only after you sync/Add |

Default risk portfolio on first config: `SPY`, `AAPL`, `MSFT`, `NVDA`, `AMZN`.

### Manual cycle (type-and-run)

1. Start the agent (paper or live) with Forecast Mode enabled.
2. Type one or more tickers (e.g. `GOOG, AMZN`).
3. Click **Run forecast cycle** — those symbols are posted to
   `POST /trading-agent/cycle` and are **not** written to `config.universe`.

**Add** still saves tickers into the risk portfolio for auto-cycles. Sync
favorites merges watchlist tickers into that saved list (subject to the 50 cap).

### Auto-cycles

When the agent is running, the backend scheduler calls `run_cycle` on
`cycle_interval_seconds` (default 300) using **only** the saved risk portfolio.
Pause / Emergency Stop halt auto-cycling.

## API (prefix `/api/v1`)

| Method | Path | Notes |
|--------|------|--------|
| GET/PUT | `/trading-agent/config` | Includes `universe`, `max_universe_size` (50), `last_universe_scan`, risk, intervals |
| POST | `/trading-agent/start` \| `pause` \| `resume` \| `emergency-stop` | Lifecycle |
| POST | `/trading-agent/cycle` | Body: `{ "symbols"?: string[], "execute": true }`. If `symbols` is set, it is validated (`normalize_universe`) and used for that run only. If omitted (`null`), uses saved universe (fallback `SPY`). Empty / invalid `symbols` → **422**. |
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
