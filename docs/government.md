# Government Contract Analysis

StockPulse ingests public U.S. government procurement data and produces explainable
**government_score** and **government_early_signal_score** values (0–100). Scores are
**research signals**, not investment advice or trading instructions.

The package lives under `backend/app/government/` and feeds the existing hybrid stack
(`FeatureSnapshot.government`, prediction matrix when enabled, Market UI panel). It is
not a separate trading subsystem. Provider failures degrade gracefully — trading,
forecasts, and quotes continue to work.

```text
SAM.gov + USAspending
    → company mapping (UEI / CAGE / CIK / name, confidence-gated)
    → normalized events (deduped by source + event_id)
    → government_score / early_signal_score (config-driven, not LLM)
    → API payload + ML features + optional UI alert banners
```

## Data sources

| Provider | Client | What it supplies |
|----------|--------|------------------|
| SAM.gov | `SamGovClient` | Opportunities and awards (notice types → normalized event types) |
| USAspending | `UsaSpendingClient` | Obligations / award spending linked to contractors |

- SAM.gov requires `SAM_GOV_API_KEY` when `GOVERNMENT_ENABLED=true`
- USAspending uses public endpoints (no API key)
- Scoring weights and alert thresholds live in [`backend/configs/government.yaml`](../backend/configs/government.yaml)

## Event types

Normalized types (pipeline + features):

| Type | Role |
|------|------|
| `PROCUREMENT_FORECAST` | Early pipeline signal |
| `SOURCES_SOUGHT` | Early pipeline signal |
| `PRESOLICITATION` | Early pipeline signal |
| `SOLICITATION` | Open opportunity |
| `AWARD` / `AWARD_MODIFICATION` | Award activity |
| `OBLIGATION` | Spending obligation |
| `OPTION_EXERCISED` | Option exercise on an existing vehicle |

## Company mapping

`GovernmentCompanyMapper` resolves contractors to tickers via UEI, CAGE, CIK, and
normalized legal name (fuzzy match with confidence gates). It reuses
`SecCompanyMapping` when helpful and persists accepted links in
`GovernmentCompanyMapping`. Low-confidence matches are not attached to a ticker.

## Scoring (deterministic)

Weights in `backend/configs/government.yaml` (defaults shown there): awards,
sole-source, large opportunities, new customer, multi-year, material revenue /
backlog impact, incumbent, plus penalties for IDIQ ceiling-only, option-only, and
immaterial contracts. Early-signal score takes the best stage weight among events
still available at `as_of` (forecast/sources-sought/presolicitation rank highest).

Scores are never computed by the LLM.

## Point-in-time

For prediction/features at timestamp `T`, only events with
`event_at <= T` **and** `published_at <= T` (when present) are used. Events missing
both timestamps are dropped. This matches the SEC flow leakage rules.

## Configuration

Add to `backend/.env` (Settings fields on `app.config.Settings`):

```dotenv
GOVERNMENT_ENABLED=true
SAM_GOV_API_KEY=
GOVERNMENT_CONFIG_PATH=backend/configs/government.yaml
GOVERNMENT_RATE_LIMIT_PER_MINUTE=30
GOVERNMENT_SYNC_ON_STARTUP=false
```

ML toggle: `features.government: true` in `ml/config/prediction.yaml`
(`feature_version` `1.1.0`).

## API endpoints

All routes use the `/api/v1` prefix and require authentication when JWT/API-key auth
is enabled.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/stocks/{symbol}/government` | Analysis payload (scores, activity, agencies, alerts). Pass `?sync=true` to refresh providers first |
| POST | `/stocks/{symbol}/government/sync` | Sync providers for the ticker, then return the same analysis shape |

Example payload shape:

```json
{
  "ticker": "LMT",
  "as_of": "2026-09-13T00:00:00+00:00",
  "government": {
    "score": 72,
    "early_signal_score": 80,
    "awards_30d": 2,
    "award_value_30d": 15000000,
    "obligations_30d": 1,
    "obligation_value_30d": 2000000,
    "opportunity_count_30d": 3,
    "opportunity_value_30d": 50000000,
    "new_customer": false,
    "sole_source": true,
    "incumbent": true,
    "multi_year": true,
    "revenue_exposure": 0.02,
    "contract_value": 15000000
  },
  "recent_activity": [],
  "open_opportunities": [],
  "recent_awards": [],
  "recent_obligations": [],
  "top_agencies": [],
  "alerts": [],
  "provider_errors": []
}
```

`alerts` are SEC-style candidate banners on the API payload and Market UI only —
no push or email delivery. Award rows may include optional `market_reaction`
(post-event bar returns) when OHLCV is available.

## UI

On the **Market** tab, `GovernmentPanel` sits alongside SEC Intelligence: overall
score, early-signal score, 30-day award/obligation/opportunity stats, flags,
recent activity, top agencies, and alert banners when thresholds fire.

## ML feature category

Point-in-time builders under `ml/features/government/` populate
`FeatureSnapshot.government` (keys such as `government_score`,
`government_early_signal_score`, award/obligation/opportunity window counts and
values, flags, `government_revenue_ratio`). When `features.government` is true,
those columns are merged into the XGBoost/LightGBM train/predict matrix.

## Persistence

| Table | Role |
|-------|------|
| `government_events` | Normalized events (`GovernmentEvent`) |
| `government_contracts` | Rolled-up contract rows (`GovernmentContract`) |
| `government_company_mappings` | UEI/CAGE/CIK/name → ticker (`GovernmentCompanyMapping`) |

## Package layout

```text
backend/app/government/
    clients/           SamGovClient, UsaSpendingClient
    config.py          YAML loader
    db_models.py       SQLAlchemy tables
    mapping.py         Company → ticker resolver
    normalize.py       Shared parsing helpers
    scoring.py         Deterministic score helpers
    market_reaction.py Optional post-event returns
    service.py         Sync + analysis payload
    types.py           Event type constants / dataclasses
backend/configs/government.yaml
ml/features/government/
backend/app/api/government.py
frontend/src/GovernmentPanel.tsx
```

## Logging

Structured messages under logger `app.government` / `app.api.government`, including
`government_events_ingested`, `government_provider_errors`, and `government_alert`.

## Tests

```bash
cd backend
pytest -q tests/test_government.py

# from repo root
pytest -q ml/tests/test_government_features.py
```

## Related

- [SEC_ACCUMULATION.md](./SEC_ACCUMULATION.md) — EDGAR ownership / accumulation
- [feature-engine.md](./feature-engine.md) — feature categories and PIT rules
- [stock-prediction-architecture.md](./stock-prediction-architecture.md) — hybrid stack
- [api.md](./api.md) — prediction API surface
