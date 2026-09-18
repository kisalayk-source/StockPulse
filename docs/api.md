# Hybrid prediction API

Base prefix: `/api/v1` (API key + authenticated user).

Plain-language MVP overview: [mvp-roadmap.md](./mvp-roadmap.md).

| Method | Path | Description |
|---|---|---|
| GET | `/stocks/{ticker}/prediction?horizon=5d` | Full hybrid prediction payload |
| GET | `/stocks/{ticker}/features` | Latest feature snapshot |
| GET | `/stocks/{ticker}/signals` | Signal + probability summary |
| GET | `/stocks/{ticker}/risk` | Signal risk assessment |
| GET | `/stocks/{ticker}/explanation` | Template/LLM explanation (MVP-7; LLM only when research AI is on) |

Horizons: `1d`, `5d`, `20d`.

Path forecast remains `POST /forecast` and is unchanged.

Env toggles: `PREDICTION_ENABLED`, `PREDICTION_RATE_LIMIT_PER_MINUTE`.
Agent alignment: hybrid owns BUY/SELL; path owns sizing/targets
(`agent_require_hybrid_signal`, default `true`).

### Autonomous Trading Agent

Full behavior (ad-hoc vs saved universe): [trading-agent.md](./trading-agent.md).

| Method | Path | Description |
|---|---|---|
| GET/PUT | `/trading-agent/config` | Agent config; `universe` (saved risk portfolio, max 50), `max_universe_size`, `last_universe_scan` |
| POST | `/trading-agent/start` | Start paper/live (`{ "mode": "paper" \| "live" }`) |
| POST | `/trading-agent/pause` \| `/resume` \| `/emergency-stop` | Lifecycle |
| POST | `/trading-agent/cycle` | One cycle. Optional `{ "symbols": ["GOOG"], "execute": true }` — ad-hoc tickers **not** required in `universe`; omit `symbols` to use the saved portfolio. Invalid/empty `symbols` → 422 |
| GET | `/trading-agent/forecasts` | Forecasts for the saved universe |
| GET | `/trading-agent/candidates` \| `/trade-plans` \| `/orders` \| `/positions` \| `/events` \| `/performance` | Run artifacts |
| GET | `/trading-agent/day-trades` | Day-trades report (`?date=YYYY-MM-DD`) |
| GET/PUT | `/trading-agent/daily-loss` | Daily loss limits; `POST /trading-agent/daily-loss/reset` |
