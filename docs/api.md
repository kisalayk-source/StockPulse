# Hybrid prediction API

Base prefix: `/api/v1` (API key + authenticated user).

| Method | Path | Description |
|---|---|---|
| GET | `/stocks/{ticker}/prediction?horizon=5d` | Full hybrid prediction payload |
| GET | `/stocks/{ticker}/features` | Latest feature snapshot |
| GET | `/stocks/{ticker}/signals` | Signal + probability summary |
| GET | `/stocks/{ticker}/risk` | Signal risk assessment |
| GET | `/stocks/{ticker}/explanation` | Template/LLM explanation |

Horizons: `1d`, `5d`, `20d`.

Path forecast remains `POST /forecast` and is unchanged.

Env toggles: `PREDICTION_ENABLED`, `PREDICTION_RATE_LIMIT_PER_MINUTE`.
