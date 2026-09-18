"""Government contract feature builders (PIT-safe)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ml.features.feature_schema import GOVERNMENT_FEATURE_KEYS, normalize_feature_dict
from ml.features.government._common import filter_government_events_as_of, to_float

AWARD_TYPES = frozenset({"AWARD", "AWARD_MODIFICATION", "OPTION_EXERCISED"})
OBLIGATION_TYPES = frozenset({"OBLIGATION"})
OPPORTUNITY_TYPES = frozenset(
    {
        "PROCUREMENT_FORECAST",
        "SOURCES_SOUGHT",
        "PRESOLICITATION",
        "SOLICITATION",
    }
)

_DEFAULT_EARLY = {
    "PROCUREMENT_FORECAST": 100.0,
    "SOURCES_SOUGHT": 90.0,
    "PRESOLICITATION": 80.0,
    "SOLICITATION": 70.0,
    "AWARD": 50.0,
    "AWARD_MODIFICATION": 45.0,
    "OBLIGATION": 30.0,
    "OPTION_EXERCISED": 35.0,
}

_DEFAULT_SCORING = {
    "award": 30.0,
    "sole_source": 20.0,
    "large_opportunity": 15.0,
    "new_customer": 10.0,
    "multi_year": 10.0,
    "material_revenue": 10.0,
    "backlog_impact": 10.0,
    "incumbent": 5.0,
    "idiq_ceiling_only": -20.0,
    "option_only": -15.0,
    "immaterial_contract": -10.0,
}


def _event_ts(event: dict[str, Any]) -> datetime | None:
    for key in ("event_at", "published_at"):
        raw = event.get(key)
        if raw is None:
            continue
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        try:
            text = str(raw).replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _in_window(event: dict[str, Any], *, as_of: datetime, days: int) -> bool:
    ts = _event_ts(event)
    if ts is None:
        return False
    return (as_of - timedelta(days=days)) <= ts <= as_of


def _material_value(event: dict[str, Any]) -> float | None:
    event_type = str(event.get("event_type") or "")
    if event_type in OBLIGATION_TYPES:
        return to_float(event.get("obligated_amount")) or to_float(event.get("transaction_amount"))
    if event_type in AWARD_TYPES:
        return to_float(event.get("awarded_amount")) or to_float(event.get("obligated_amount"))
    if event_type in OPPORTUNITY_TYPES:
        return to_float(event.get("estimated_value")) or to_float(event.get("awarded_amount"))
    return None


def compute_government_features(
    events: list[dict[str, Any]],
    *,
    as_of: datetime,
    annual_revenue: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Compute government feature vector using only events available at ``as_of``."""
    cfg = config or {}
    scoring = {**_DEFAULT_SCORING, **(cfg.get("scoring") or {})}
    early_map = {**_DEFAULT_EARLY, **(cfg.get("early_signal") or {})}
    thresholds = cfg.get("thresholds") or {}
    large_opp = float(thresholds.get("large_opportunity_amount", 50_000_000))
    material_ratio = float(thresholds.get("material_revenue_ratio", 0.05))
    immaterial_ratio = float(thresholds.get("immaterial_revenue_ratio", 0.005))
    multi_year_days = int(thresholds.get("multi_year_days", 365))

    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    pit = filter_government_events_as_of(events, as_of)

    def window_stats(types: frozenset[str], days: int, amount_getter) -> tuple[float, float]:
        count = 0.0
        total = 0.0
        for event in pit:
            if event.get("event_type") not in types:
                continue
            if not _in_window(event, as_of=as_of, days=days):
                continue
            count += 1.0
            value = amount_getter(event)
            if value is not None:
                total += float(value)
        return count, total

    award_7, award_val_7 = window_stats(AWARD_TYPES, 7, lambda e: to_float(e.get("awarded_amount")))
    award_30, award_val_30 = window_stats(AWARD_TYPES, 30, lambda e: to_float(e.get("awarded_amount")))
    award_90, award_val_90 = window_stats(AWARD_TYPES, 90, lambda e: to_float(e.get("awarded_amount")))
    obl_7, obl_val_7 = window_stats(OBLIGATION_TYPES, 7, lambda e: to_float(e.get("obligated_amount")))
    obl_30, obl_val_30 = window_stats(OBLIGATION_TYPES, 30, lambda e: to_float(e.get("obligated_amount")))
    obl_90, obl_val_90 = window_stats(OBLIGATION_TYPES, 90, lambda e: to_float(e.get("obligated_amount")))
    opp_30, opp_val_30 = window_stats(
        OPPORTUNITY_TYPES,
        30,
        lambda e: to_float(e.get("estimated_value")) or to_float(e.get("ceiling_amount")),
    )

    score = 0.0
    new_customer = 0.0
    incumbent = 0.0
    sole_source = 0.0
    multi_year = 0.0
    agencies_awarded: set[str] = set()
    early_best = 0.0
    revenue_ratios: list[float] = []

    historical_agencies: set[str] = set()
    for event in pit:
        ts = _event_ts(event)
        if ts and ts < as_of - timedelta(days=90) and event.get("event_type") in AWARD_TYPES:
            if event.get("agency"):
                historical_agencies.add(str(event["agency"]).lower())

    for event in pit:
        event_type = str(event.get("event_type") or "")
        early_best = max(early_best, float(early_map.get(event_type, 0.0)))
        agency = str(event.get("agency") or "").strip()

        if event_type in AWARD_TYPES:
            score += float(scoring["award"])
            if agency:
                agencies_awarded.add(agency.lower())
                if agency.lower() not in historical_agencies:
                    new_customer = 1.0
                    score += float(scoring["new_customer"])
            incumbent = 1.0

        if event.get("sole_source"):
            sole_source = 1.0
            score += float(scoring["sole_source"])

        if event_type in OPPORTUNITY_TYPES:
            est = to_float(event.get("estimated_value")) or to_float(event.get("ceiling_amount"))
            if est is not None and est >= large_opp:
                score += float(scoring["large_opportunity"])

        start = event.get("period_start")
        end = event.get("period_end")
        if start and end:
            try:
                s = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
                e = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                if (e - s).days >= multi_year_days:
                    multi_year = 1.0
                    score += float(scoring["multi_year"])
            except Exception:
                pass

        mat = _material_value(event)
        if mat is not None and annual_revenue and annual_revenue > 0:
            ratio = mat / float(annual_revenue)
            revenue_ratios.append(ratio)
            if ratio >= material_ratio:
                score += float(scoring["material_revenue"])
                score += float(scoring["backlog_impact"])
            elif ratio < immaterial_ratio:
                score += float(scoring["immaterial_contract"])

        ceiling = to_float(event.get("ceiling_amount"))
        awarded = to_float(event.get("awarded_amount"))
        obligated = to_float(event.get("obligated_amount"))
        if event.get("idiq") and ceiling and not awarded and not obligated:
            score += float(scoring["idiq_ceiling_only"])

        if event.get("option_only") or event_type == "OPTION_EXERCISED":
            score += float(scoring["option_only"])

    if incumbent:
        score += float(scoring["incumbent"])

    revenue_ratio = max(revenue_ratios) if revenue_ratios else None

    values: dict[str, float | None] = {
        "government_award_count_7d": award_7,
        "government_award_count_30d": award_30,
        "government_award_count_90d": award_90,
        "government_award_value_7d": award_val_7,
        "government_award_value_30d": award_val_30,
        "government_award_value_90d": award_val_90,
        "government_obligation_value_7d": obl_val_7,
        "government_obligation_value_30d": obl_val_30,
        "government_obligation_value_90d": obl_val_90,
        "government_opportunity_count_30d": opp_30,
        "government_opportunity_value_30d": opp_val_30,
        "government_score": min(100.0, max(0.0, score)),
        "government_early_signal_score": min(100.0, max(0.0, early_best)),
        "government_new_customer": new_customer,
        "government_incumbent": incumbent,
        "government_sole_source": sole_source,
        "government_multi_year": multi_year,
        "government_revenue_ratio": revenue_ratio,
    }
    # Ensure schema keys present when computable; normalize drops nulls
    normalized = normalize_feature_dict(values)
    for key in GOVERNMENT_FEATURE_KEYS:
        if key not in normalized and values.get(key) is not None:
            normalized[key] = float(values[key])  # type: ignore[arg-type]
    return normalized
