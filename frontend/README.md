# StockPulse Frontend

Responsive React/TypeScript dashboard for personal Alpaca trading and Kronos forecast research.

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

## API contract

The typed client in `src/api.ts` models:

- `GET /health`, `GET /ready`, `GET /config/status`
- `GET /market/clock`
- `GET /symbols/search?q=`
- `GET /stocks/:symbol/overview`
- `GET /stocks/:symbol/bars?timeframe=&limit=`
- `POST /forecast`, `POST /forecast/movers`, `GET /forecast/movers/status`
- `GET /account?mode=`, `/positions?mode=`, `/orders?mode=`
- `GET /options/contracts?underlying=&mode=` and `GET /options/chain?underlying=`
- `POST /orders/preview`, `POST /orders/equity`, `POST /orders/option`
- `DELETE /orders/:id`, `PATCH /orders/:id`

All order and account requests explicitly carry `paper` or `live` mode. The adapters in
`src/api.ts` normalize the backend's snake_case Alpaca payloads for the React components.

## Safety

Live mode requires typing `LIVE` before it can be enabled, remains visibly marked, and every order
opens a separate final review dialog. Forecasts are display-only and have no path to order
submission. This UI does not replace broker-side controls, account permissions, or server-side
validation.

The interface also blocks risk-rejected previews, disables live mode when the server disallows
it, ignores stale option-chain and market responses, reports partial-data failures, supports
keyboard-dismissable dialogs, and automatically dismisses order notices.
Potential gainers and losers appear progressively while the background Kronos universe scan
runs, with visible scanned/total progress and automatic polling.
