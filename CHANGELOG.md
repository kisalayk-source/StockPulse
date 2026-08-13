# Changelog

Notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Open-source community health, CI, dependency update, development, licensing,
  and reproducible container deployment documentation.
- StockPulse risk previews, explicit option position intent, cancel/replace APIs,
  request IDs, structured audit logging, readiness checks, and rate limits.
- Progressive background mover scans with independently ranked top-50 potential
  gainers and losers.
- Production-grade historical backtester (`kronos_backtest`) with look-ahead
  guards, next-bar execution, costs, walk-forward evaluation, and audit logs.
- Responsive error, loading, partial-data, keyboard, screen-reader, and reduced-motion
  states across the trading dashboard.

### Fixed

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
