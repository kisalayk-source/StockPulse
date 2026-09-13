# Logging (Elasticsearch + Kibana)

StockPulse emits **structured JSON logs** from the backend and browser. View them in
the terminal / `runtime-logs/`, or ship them into a **free local Elastic stack**
(Elasticsearch + Kibana) for search and dashboards.

This is the how-to. Architecture notes also live under
[observability.md](./observability.md) (same topic; prefer this guide for day-to-day use).

## What is logged

| Source | Examples |
|--------|----------|
| Backend HTTP | `request_completed` / `request_failed` with `request_id`, method, path, status, `duration_ms` |
| Trading agent | Scheduler ticks, auto-cycle, risk auto-adjust, order events |
| Frontend | Boot, API errors (5xx / trading-agent), React error boundary, `window.onerror`, unhandled rejections |

Log lines are ECS-oriented JSON, for example:

```json
{
  "@timestamp": "2026-09-11T20:00:00+00:00",
  "log.level": "INFO",
  "log.logger": "app.requests",
  "message": "request_completed",
  "service.name": "stockpulse",
  "trace.id": "…",
  "http.request.method": "GET",
  "url.path": "/api/v1/health",
  "http.response.status_code": 200,
  "duration_ms": 4.2
}
```

Frontend events are posted to `POST /api/v1/logs/client` and re-emitted by the
backend logger `app.frontend` (same Elastic index when shipping is enabled).
The ingest endpoint is rate-limited (120 requests/minute per client) and uses the
same optional `X-API-Key` gate as other API routes (no user JWT required, so boot
errors still report).

## Quick start (local Elastic — free)

Requires Docker with Compose v2. **Default for StockPulse:** local compose with
security disabled (dev/LAN only).

```powershell
# From repo root — start only Elasticsearch + Kibana
docker compose --profile observability up -d elasticsearch kibana
```

Wait until Elasticsearch answers:

```powershell
curl http://127.0.0.1:9200
```

Open Kibana: [http://127.0.0.1:5601](http://127.0.0.1:5601)

### Point StockPulse at Elastic

In `backend/.env` (copy from `.env.example` if needed):

```env
LOG_LEVEL=INFO
ELASTICSEARCH_ENABLED=true
ELASTICSEARCH_URL=http://127.0.0.1:9200
ELASTICSEARCH_INDEX=stockpulse-logs
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `LOG_LEVEL` | `INFO` | Console + Elastic level |
| `ELASTICSEARCH_ENABLED` | `false` | Opt-in shipper (app starts fine when off) |
| `ELASTICSEARCH_URL` | unset / example `http://127.0.0.1:9200` | Cluster URL |
| `ELASTICSEARCH_INDEX` | `stockpulse-logs` | Bulk index name |

For Docker Compose **backend** on the same compose network, use:

```env
ELASTICSEARCH_URL=http://elasticsearch:9200
ELASTICSEARCH_ENABLED=true
```

Restart the API (or re-run `scripts/publish-kronos-lan.ps1`) so the shipper starts.

LAN publish writes files under `runtime-logs/` **and** (when enabled) bulk-indexes
into Elasticsearch in the background. If Elastic is down, the app keeps running;
logs still go to stdout / files.

## Kibana: create a data view

1. Open Kibana → **Management** → **Stack Management** → **Data Views** (or **Discover**).
2. Create a data view with index pattern: `stockpulse-logs*`
3. Time field: `@timestamp`
4. Open **Discover** and filter, e.g.:
   - `service.name: "stockpulse"`
   - `log.logger: "app.frontend"`
   - `message: "api_error"`
   - `trace.id: "<request id from UI / response header>"`

### Useful Discover queries

```text
log.logger: "app.trading_agent.scheduler" or message: "trading_agent_auto_cycle*"
source: "frontend" and log.level: "ERROR"
url.path: "/api/v1/trading-agent/*"
```

## Frontend usage (for developers)

```ts
import { appLog } from './logging'

appLog.info('agent_started_ui')
appLog.warn('unexpected_state', { symbol: 'NVDA' })
appLog.error('cycle_failed', { runId }, err)
```

Logs are batched (~2s or 20 events) to `POST /api/v1/logs/client`.
`X-Request-ID` from API responses is attached for correlation.

## Backend usage

```python
import logging
logger = logging.getLogger("app.my_feature")
logger.info("something_happened", extra={"symbol": "AAPL", "request_id": "…"})
```

Use the `app.*` logger namespace so handlers and Elastic shipping apply.

## Compose reference

| Service | Port | Profile |
|---------|------|---------|
| elasticsearch | `127.0.0.1:9200` | `observability` |
| kibana | `127.0.0.1:5601` | `observability` |

Stop the stack:

```powershell
docker compose --profile observability down
```

Data volume: `elasticsearch-data` (persists indices across restarts).

## Security notes

- This local profile runs Elastic **with security disabled** for developer convenience.
  Do **not** expose ports `9200` / `5601` on the public internet.
- For a shared/team cluster, enable Elastic security (or Elastic Cloud free trial),
  put credentials in env (not committed), and keep Kibana behind VPN or auth.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No docs in Discover | Confirm `ELASTICSEARCH_ENABLED=true`, API restarted, index `stockpulse-logs` exists (`GET /_cat/indices`) |
| Kibana empty | Create data view on `stockpulse-logs*` with `@timestamp` |
| Frontend logs missing | Network tab: `POST /api/v1/logs/client` → 200; rate limit is 120/min |
| High memory | Lower `ES_JAVA_OPTS` in `compose.yaml` (default `-Xms512m -Xmx512m`) |
| App won't start | Elastic is optional — leave `ELASTICSEARCH_ENABLED=false` (default) |

## Related

- LAN runtime log files: [DEVELOPMENT.md](./DEVELOPMENT.md)
- Request middleware: `backend/app/main.py`
- Logging module: `backend/app/logging.py`
- Client ingest: `backend/app/api/logs.py`
- Client logger: `frontend/src/logging.ts`
