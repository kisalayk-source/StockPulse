"""Deterministic government contract scoring (config-driven)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.government.types import (
    AWARD_TYPES,
    OBLIGATION_TYPES,
    OPPORTUNITY_TYPES,
    NormalizedGovernmentEvent,
)


def _as_event_dict(event: NormalizedGovernmentEvent | dict[str, Any]) -> dict[str, Any]:
    if isinstance(event, NormalizedGovernmentEvent):
        return event.to_dict()
    return dict(event)


def materiality_value(event: dict[str, Any]) -> float | None:
    """Value used for revenue materiality — never IDIQ ceiling alone."""
    event_type = str(event.get("event_type") or "")
    if event_type in OBLIGATION_TYPES:
        for key in ("obligated_amount", "transaction_amount"):
            value = event.get(key)
            if value is not None:
                return float(value)
        return None
    if event_type in AWARD_TYPES:
        for key in ("awarded_amount", "obligated_amount", "transaction_amount"):
            value = event.get(key)
            if value is not None:
                return float(value)
        # Ceiling-only awards are not treated as realized value
        return None
    if event_type in OPPORTUNITY_TYPES:
        for key in ("estimated_value", "awarded_amount"):
            value = event.get(key)
            if value is not None:
                return float(value)
        return None
    return None


def revenue_ratio(event: dict[str, Any], annual_revenue: float | None) -> float | None:
    if annual_revenue is None or annual_revenue <= 0:
        return None
    value = materiality_value(event)
    if value is None:
        return None
    return float(value) / float(annual_revenue)


def is_multi_year(event: dict[str, Any], *, multi_year_days: int = 365) -> bool:
    start = event.get("period_start")
    end = event.get("period_end")
    if not start or not end:
        return False
    try:
        if isinstance(start, str):
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        else:
            start_dt = start
        if isinstance(end, str):
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        else:
            end_dt = end
        return (end_dt - start_dt).days >= multi_year_days
    except Exception:
        return False


def early_signal_score_for_events(
    events: list[dict[str, Any]] | list[NormalizedGovernmentEvent],
    config: dict[str, Any],
) -> float:
    early_map = config.get("early_signal") or {}
    best = 0.0
    for raw in events:
        event = _as_event_dict(raw)
        event_type = str(event.get("event_type") or "")
        score = float(early_map.get(event_type, 0))
        if score > best:
            best = score
    return round(min(100.0, max(0.0, best)), 2)


def compute_government_score(
    events: list[dict[str, Any]] | list[NormalizedGovernmentEvent],
    *,
    config: dict[str, Any],
    annual_revenue: float | None = None,
    known_agencies: set[str] | None = None,
    incumbent_contracts: int = 0,
) -> dict[str, Any]:
    """Return score 0–100 plus component flags used by features/alerts."""
    weights = config.get("scoring") or {}
    thresholds = config.get("thresholds") or {}
    large_opp = float(thresholds.get("large_opportunity_amount", 50_000_000))
    material_ratio = float(thresholds.get("material_revenue_ratio", 0.05))
    immaterial_ratio = float(thresholds.get("immaterial_revenue_ratio", 0.005))
    multi_year_days = int(thresholds.get("multi_year_days", 365))

    score = 0.0
    flags = {
        "new_customer": False,
        "sole_source": False,
        "incumbent": incumbent_contracts > 0,
        "multi_year": False,
        "idiq_ceiling_only": False,
        "option_only": False,
        "material_revenue": False,
        "large_opportunity": False,
        "has_award": False,
    }

    agencies_seen: set[str] = set()
    known = {a.lower() for a in (known_agencies or set()) if a}

    for raw in events:
        event = _as_event_dict(raw)
        event_type = str(event.get("event_type") or "")
        agency = str(event.get("agency") or "").strip()
        if agency:
            agencies_seen.add(agency.lower())

        if event_type in AWARD_TYPES:
            flags["has_award"] = True
            score += float(weights.get("award", 30))

        if event.get("sole_source"):
            flags["sole_source"] = True
            score += float(weights.get("sole_source", 20))

        if event_type in OPPORTUNITY_TYPES:
            est = event.get("estimated_value") or event.get("ceiling_amount") or event.get("awarded_amount")
            if est is not None and float(est) >= large_opp:
                flags["large_opportunity"] = True
                score += float(weights.get("large_opportunity", 15))

        if agency and agency.lower() not in known and known:
            flags["new_customer"] = True
            score += float(weights.get("new_customer", 10))
        elif agency and not known:
            # First observed agency for ticker treated as new customer signal once
            flags["new_customer"] = True
            score += float(weights.get("new_customer", 10))
            known.add(agency.lower())

        if is_multi_year(event, multi_year_days=multi_year_days) or event.get("multi_year"):
            flags["multi_year"] = True
            score += float(weights.get("multi_year", 10))

        ratio = revenue_ratio(event, annual_revenue)
        if ratio is not None:
            if ratio >= material_ratio:
                flags["material_revenue"] = True
                score += float(weights.get("material_revenue", 10))
                score += float(weights.get("backlog_impact", 10))
            elif ratio < immaterial_ratio:
                score += float(weights.get("immaterial_contract", -10))

        ceiling = event.get("ceiling_amount")
        awarded = event.get("awarded_amount")
        obligated = event.get("obligated_amount")
        if event.get("idiq") and ceiling and not awarded and not obligated:
            flags["idiq_ceiling_only"] = True
            score += float(weights.get("idiq_ceiling_only", -20))

        if event.get("option_only") or event_type == "OPTION_EXERCISED":
            flags["option_only"] = True
            score += float(weights.get("option_only", -15))

    if flags["incumbent"]:
        score += float(weights.get("incumbent", 5))

    clamped = round(min(100.0, max(0.0, score)), 2)
    early = early_signal_score_for_events(events, config)
    return {
        "government_score": clamped,
        "government_early_signal_score": early,
        "flags": flags,
        "agencies": sorted(agencies_seen),
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
