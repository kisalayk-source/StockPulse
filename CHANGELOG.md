# Changelog

Notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **SEC market tabs** — background accumulation scan (blue-chip + movers universe) populates Sectors, Top Accumulation, and AI Research; new **SEC Records** tab for 6-month filing search; sector names normalized from Finnhub profiles.
- Chart interval control (1m / 5m / 15m / 1h / 1D) for historical candles and
  forecasts; Short/Long horizons restored to original 12 and 20 bars (bar-count
  chips removed).
- Kronos forecasts average multiple lower-temperature samples by default
  (`KRONOS_SAMPLE_COUNT=5`, `KRONOS_TEMPERATURE=0.6`, `KRONOS_TOP_P=0.9`) for
  smoother chart paths in both Kronos and Forecast (ensemble) modes.

### Added

- **SEC EDGAR + Accumulation Score** — server-side SEC client (`backend/app/sec/`), 13F/13D/13G/Form 4 parsers, explainable Accumulation Score (0–100) with configurable weights (`backend/configs/sec_accumulation.yaml`), REST endpoints (per-ticker SEC, `/accumulation/top`, `/sectors`, `/accumulation/scan`, `/stocks/{symbol}/filings`, `/research/query`), optional OpenAI-compatible research narration, SQLite persistence, look-ahead-safe accumulation backtest foundation, and dashboard tabs (SEC Intelligence, Sectors, Top Accumulation, SEC Records, AI Research). See [docs/SEC_ACCUMULATION.md](./docs/SEC_ACCUMULATION.md).
- Guide PDF `docs/StockPulse-Finance-Glossary.pdf` expanded with StockPulse cost,
  edge, portfolio-weight, and order-risk formulas plus default risk limits.
- Chart **Kronos / Forecast** toggle: Kronos mode uses the single Kronos model;
  Forecast mode runs the multi-model weighted ensemble through StockPulse
  `POST /api/v1/forecast` (`engine=ensemble`) so LAN publish stays on one stack;
  movers remain Kronos-only.
- Model-agnostic research forecasting package (`forecasting/`) with a shared
  `ForecastModel` contract, config-driven registry (`config/models.yaml`),
  Kronos/Chronos/TimesFM/Lag-Llama adapters, weighted and inverse-error
  ensembles, walk-forward eval harness, and a thin research FastAPI entrypoint
  (`forecasting.api.serve`) that does not replace StockPulse `/forecast`.
- Guide PDFs: `docs/StockPulse-Architecture.pdf` (webapp technical architecture)
  and `docs/StockPulse-Finance-Glossary.pdf` (dashboard finance terms). Rebuild
  with `scripts/build-guide-pdfs.ps1`.
- Selectable forecast bar counts (1 / 10 / 20 / 30 / 60) on Short (5-minute) and
  Long (daily) horizons, with a decision panel under the chart for path turns plus
  bull/bear context from news and regime.
- Open-source community health, CI, dependency update, development, licensing,
  and reproducible container deployment documentation.
- StockPulse risk previews, explicit option position intent, cancel/replace APIs,
  request IDs, structured audit logging, readiness checks, and rate limits.
- Progressive background mover scans with independently ranked top-50 potential
  gainers and losers.
- Full-width open-positions panel under the movers scan.
- Production-grade historical backtester (`kronos_backtest`) with look-ahead
  guards, next-bar execution, costs, walk-forward evaluation, and audit logs.
- Responsive error, loading, partial-data, keyboard, screen-reader, and reduced-motion
  states across the trading dashboard.

### Fixed

- **SEC Records empty for valid tickers** — `/stocks/{symbol}/filings` syncs EDGAR submissions before querying SQLite; the SEC Records tab auto-loads on open and after search.
- **LAN 502 on first load** — publish script waits for backend health before starting the frontend; accumulation scan no longer blocks API requests while building the mover universe.
- **Sparse Sectors / Top tabs** — market-wide tabs read from the accumulation score cache populated by the background scan, not only the active Market symbol.
- **Raw score enums in tables** — Top Accumulation and AI Research show human-readable classification labels (e.g. `Strong Accumulation`) instead of `STRONG_ACCUMULATION`.
- Ticker forecasts no longer share the movers-scan rate-limit bucket, so switching
  symbols during a scan no longer shows "Partial data. forecast data is temporarily
  unavailable."
- Corrected spread basis-point units, average-volume calculation, stale frontend
  responses, paper-only option-chain requests, and incomplete movers rendering.

### Security

- Added optional API-key authentication, loopback-safe launch defaults, restricted
  CORS, constant-time confirmation checks, generic provider errors, and sell-side
  position controls.

## Versioning policy

- `MAJOR` releases contain incompatible public API, model interface, data
  format, or deployment changes.
- `MINOR` releases add backward-compatible capabilities.
- `PATCH` releases contain backward-compatible fixes and documentation updates.
- Pre-1.0 releases may evolve quickly; breaking changes must still be called
  out in this changelog and pull request.

Model weights and tokenizer artifacts are versioned independently on their
hosting service. Reproducible tests should pin artifact revisions rather than
relying only on repository release tags.

To release, move entries from `Unreleased` into a dated `X.Y.Z` section, create
an annotated `vX.Y.Z` tag from the reviewed default branch, and publish matching
GitHub release notes.
