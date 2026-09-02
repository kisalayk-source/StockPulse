# StockPulse Frontend

Responsive React/TypeScript dashboard for personal Alpaca trading, Kronos path-forecast research, hybrid BUY/HOLD/SELL signals, and SEC accumulation intelligence.

## Setup

```bash
npm install
copy .env.example .env.local
npm run dev
```

Set `VITE_API_BASE_URL` to the backend API prefix. It defaults to the same-origin `/api/v1`
path proxied by Vite. If the backend is configured with `API_KEY`, set the matching
`VITE_API_KEY` only in a private deployment environment; browser-delivered keys are not a
substitute for network access controls or a proper user-authentication system.

## Commands

- `npm run dev` — Vite development server
- `npm run test` — Vitest and Testing Library suite
- `npm run typecheck` — strict TypeScript project check
- `npm run lint` — Oxlint
- `npm run build` — typecheck and production bundle

## Dashboard views

The UI is a single-page workstation with top-level tabs:

| Tab | Contents |
|-----|----------|
| **Market** | Quote, chart, path forecasts, hybrid signal panel, news, **SEC & Ownership Intelligence** panel for the active symbol |
| **Sectors** | Average accumulation score and % increasing/decreasing by sector |
| **Top Accumulation** | Ranked stocks with institutional, insider, and fundamentals component scores (from market scan) |
| **SEC Records** | Ticker search; filings from the last 6 months with filing entity, action (bought/sold/new investment), expandable parsed XML details (**+**), AI analysis card, stat chips, and EDGAR links (syncs on tab open and search) |
| **AI Research** | Natural-language query box; candidate table, filters, and evidence-backed narrative |

On login the UI starts a background market scan (blue-chip + movers) and shows progress on Sectors, Top, and Research tabs until scores populate.

The **SEC Intelligence** panel shows Accumulation Score (0–100), component bars, trend history, recent institutional/insider activity, filing caveats, and a disclaimer that scores are research signals — not trade instructions.

## API contract

The typed client in `src/api.ts` models:

- `GET /health`, `GET /ready`, `GET /config/status`
- `GET /market/clock`
- `GET /symbols/search?q=`
- `GET /stocks/:symbol/overview`
- `GET /stocks/:symbol/bars?timeframe=&limit=`
- `GET /stocks/:symbol/sec` — full SEC intelligence
- `GET /stocks/:symbol/institutional` — 13F position changes
- `GET /stocks/:symbol/insiders` — Form 4 transactions
- `GET /stocks/:symbol/accumulation` — score, components, history
- `GET /stocks/:symbol/filings?months=&limit=` — recent SEC filing history (`filer_name`, `action`, `action_tone`, `details[]`)
- `GET /stocks/:symbol/filings/analysis?months=` — AI/rule-based filing summary (sentiment, gist, highlights)
- `GET /sectors` — sector list with ticker counts
- `GET /sectors/:sector/accumulation` — sector aggregates
- `GET /accumulation/top?sector=&min_score=&limit=` — ranked stocks
- `POST /accumulation/scan` — start market accumulation scan
- `GET /accumulation/scan/status` — scan progress
- `POST /research/query` — NL research query
- `POST /forecast`, `POST /forecast/movers`, `GET /forecast/movers/status`
- `GET /account?mode=`, `/positions?mode=`, `/orders?mode=`
- `GET /options/contracts?underlying=&mode=` and `GET /options/chain?underlying=`
- `POST /orders/preview`, `POST /orders/equity`, `POST /orders/option`
- `DELETE /orders/:id`, `PATCH /orders/:id`

Components: `SecIntelligencePanel.tsx` (also exports `SectorsPanel`, `TopAccumulationPanel`, `ResearchPanel`, `SecRecordsPanel`).

All order and account requests explicitly carry `paper` or `live` mode. The adapters in
`src/api.ts` normalize the backend's snake_case payloads for the React components.

## Safety

Live mode requires typing `LIVE` before it can be enabled, remains visibly marked, and every order
opens a separate final review dialog. Forecasts and accumulation scores are display-only and have
no path to order submission. This UI does not replace broker-side controls, account permissions,
or server-side validation.

SEC panels use muted styling when provider data is partial or stale. Filing caveats remind users
that 13F holdings are quarterly reported positions — not real-time trade activity.

### Troubleshooting

- **502 Bad Gateway** on `/api/v1/*` — the Vite proxy could not reach the API. Confirm `http://127.0.0.1:8000/api/v1/health` responds; republish with `scripts/publish-kronos-lan.ps1`.
- **Empty Sectors / Top Accumulation** — wait for the background accumulation scan (progress banner) or hit dashboard Refresh.
- **SEC Records** — search by ticker; results cover the last 6 months with filing entity, action labels, expandable parsed XML details, and an AI analysis card (rule-based when LLM is off). If columns are empty, re-search to trigger XML backfill. Check `provider_errors` in the API response if sync fails.
- **Signal labels** — tables show readable classifications (e.g. `Strong Accumulation`) instead of raw enum codes.

The interface also blocks risk-rejected previews, disables live mode when the server disallows
it, ignores stale option-chain and market responses, reports partial-data failures, supports
keyboard-dismissable dialogs, and automatically dismisses order notices.
Potential gainers and losers appear progressively while the background Kronos universe scan
runs, with visible scanned/total progress and automatic polling.

See [docs/SEC_ACCUMULATION.md](../docs/SEC_ACCUMULATION.md) for scoring methodology.
