from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.sec.config_loader import get_sec_config
from app.sec.engines.confirmation import score_fundamentals, score_price_volume
from app.sec.engines.institutional import score_institutional
from app.sec.engines.insider import score_insider
from app.sec.engines.major_holder import score_major_holder
from app.sec.models import NormalizedEvent


def classify_score(score: float, config: dict[str, Any]) -> str:
    bands = config.get("score_bands", {})
    for band in bands.values():
        if band["min"] <= score <= band["max"]:
            return str(band["label"])
    if score >= 80:
        return "STRONG_ACCUMULATION"
    if score >= 60:
        return "ACCUMULATION"
    if score >= 40:
        return "NEUTRAL"
    if score >= 20:
        return "DISTRIBUTION"
    return "VERY_STRONG_DISTRIBUTION"


def signal_from_score(score: float) -> str:
    if score >= 60:
        return "ACCUMULATION"
    if score <= 39:
        return "DISTRIBUTION"
    return "NEUTRAL"


def compute_accumulation_score(
    events: list[NormalizedEvent],
    bars: list[dict[str, Any]],
    fundamentals: dict[str, float | None],
    config: dict[str, Any] | None = None,
    spy_bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    weights = cfg.get("component_weights", {})
    components: dict[str, float] = {}
    evidence_positive: list[str] = []
    evidence_negative: list[str] = []

    inst_score, inst_ev = score_institutional(events, cfg)
    insider_score, insider_ev = score_insider(events, cfg)
    major_score, major_ev = score_major_holder(events, cfg)
    pv_score, pv_ev = score_price_volume(bars, spy_bars)
    fund_score, fund_ev = score_fundamentals(fundamentals)

    components = {
        "institutional": round(inst_score, 1),
        "insider": round(insider_score, 1),
        "major_holder": round(major_score, 1),
        "price_volume": round(pv_score, 1),
        "fundamentals": round(fund_score, 1),
    }
    for item in inst_ev + insider_ev + major_ev + pv_ev + fund_ev:
        if item.startswith("+"):
            evidence_positive.append(item[2:].strip())
        elif item.startswith("-"):
            evidence_negative.append(item[2:].strip())
        elif item.startswith("  "):
            evidence_positive.append(item.strip())

    active_weight = 0.0
    weighted = 0.0
    for key, value in components.items():
        weight = float(weights.get(key, 0.0))
        if value == 50.0 and key in {"price_volume", "fundamentals"} and not bars and key == "price_volume":
            continue
        active_weight += weight
        weighted += value * weight
    overall = weighted / active_weight if active_weight else 50.0
    overall = max(0.0, min(100.0, overall))
    return {
        "score": round(overall, 1),
        "signal": signal_from_score(overall),
        "classification": classify_score(overall, cfg),
        "components": components,
        "evidence": {
            "positive": evidence_positive,
            "negative": evidence_negative,
        },
    }


def persist_score_snapshot(session, ticker: str, payload: dict[str, Any]) -> None:
    from app.sec.db_models import AccumulationScore

    today = date.today()
    row = (
        session.query(AccumulationScore)
        .filter(AccumulationScore.ticker == ticker.upper(), AccumulationScore.score_date == today)
        .one_or_none()
    )
    if row is None:
        row = AccumulationScore(
            ticker=ticker.upper(),
            score_date=today,
            score=payload["score"],
            signal=payload["signal"],
            classification=payload["classification"],
            components_json=json.dumps(payload["components"]),
        )
        session.add(row)
    else:
        row.score = payload["score"]
        row.signal = payload["signal"]
        row.classification = payload["classification"]
        row.components_json = json.dumps(payload["components"])
    session.flush()
