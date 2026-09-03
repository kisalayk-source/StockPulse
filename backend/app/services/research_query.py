from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.dependencies import Services
from app.models import UserFavorite
from app.sec.scan import build_scan_universe
from app.sec.sectors import sector_matches

logger = logging.getLogger("app.services.research_query")

SECTOR_KEYWORDS = {
    "energy": "Energy",
    "technology": "Technology",
    "tech": "Technology",
    "healthcare": "Healthcare",
    "health": "Healthcare",
    "financial": "Financials",
    "finance": "Financials",
    "consumer": "Consumer Cyclical",
    "industrial": "Industrials",
    "utilities": "Utilities",
    "materials": "Materials",
    "real estate": "Real Estate",
}

DISCLAIMER = (
    "Research output ranks candidates using chart-path forecasts and model-stance probabilities, "
    "with SEC accumulation as secondary context. It is not investment advice or a trading instruction."
)

FORECAST_ENRICH_CAP = 5


def parse_research_query(query: str) -> dict[str, Any]:
    lower = query.lower()
    filters: dict[str, Any] = {}
    sector = None
    for keyword, label in SECTOR_KEYWORDS.items():
        if keyword in lower:
            sector = label
            break
    if sector:
        filters["sector"] = sector
    if "institutional" in lower or "institutions" in lower:
        if any(word in lower for word in ("accumul", "buy", "strong", "increas")):
            filters["institutional_accumulation"] = "strong"
    if "insider" in lower and any(word in lower for word in ("accumul", "buy", "positive", "purchase")):
        filters["insider_accumulation"] = "positive"
    if "distribution" in lower or "selling" in lower:
        filters["signal"] = "DISTRIBUTION"
    elif "accumulation" in lower or "accumulating" in lower:
        filters["signal"] = "ACCUMULATION"
    if any(phrase in lower for phrase in ("10 years", "long term", "long-term", "decade")):
        filters["horizon"] = "long_term"
    if re.search(r"\btop\b|\bbest\b|\bhot\b|\bleaders?\b", lower):
        filters["ranking"] = "top"
    if "favorite" in lower or "favourite" in lower or "watchlist" in lower:
        filters["favorites_only"] = True
    return {"sector": sector, "filters": filters}


def _template_narrative(
    query: str,
    candidates: list[dict[str, Any]],
    filters: dict[str, Any],
    *,
    fallback: bool = False,
) -> str:
    if not candidates:
        return (
            f"No candidates matched the parsed filters {json.dumps(filters)} for your query. "
            "Try a broader sector, add favorites, or wait for market data to load."
        )
    lines = ["Top forecast-ranked candidates", ""]
    if fallback:
        lines.append("Some forecast enrichments failed; showing best available ranked matches.")
        lines.append("")
    for idx, item in enumerate(candidates[:5], start=1):
        stance = item.get("model_stance") or "n/a"
        probability = item.get("model_probability")
        path_bias = item.get("chart_path_bias") or "n/a"
        path_change = item.get("path_change")
        prob_txt = f"{float(probability) * 100:.0f}%" if isinstance(probability, (int, float)) else "n/a"
        change_txt = f"{float(path_change) * 100:.2f}%" if isinstance(path_change, (int, float)) else "n/a"
        lines.append(
            f"{idx}. {item['ticker']}\n"
            f"   Model stance: {stance} (P(up) {prob_txt})\n"
            f"   Chart path bias: {path_bias} (path move {change_txt})"
        )
        if item.get("why"):
            lines.append(f"   Why: {item['why']}")
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


async def _llm_narrative(settings, structured: dict[str, Any], user: Any | None = None) -> str | None:
    from app.services.openai_client import call_openai_chat

    system_prompt = (
        "You explain stock research using ONLY the JSON context provided. "
        "Never invent tickers, probabilities, path moves, or filings. "
        "Emphasize model stance and chart path bias from the candidates. "
        "Cite evidence from the context. Include that this is a research signal, not trading advice."
    )
    return await call_openai_chat(
        settings,
        system_prompt=system_prompt,
        user_content=f"Query: {structured['query']}\nContext:\n{json.dumps(structured, indent=2)}",
        temperature=0.2,
        log_key="research_llm_failed",
        user=user,
    )


def _candidate_universe(
    session: Session,
    services: Services,
    *,
    sector: str | None,
    user: Any | None,
    favorites_only: bool,
) -> list[str]:
    favorites: list[str] = []
    if user is not None:
        favorites = [
            row.ticker
            for row in session.query(UserFavorite)
            .filter(UserFavorite.user_id == user.id)
            .order_by(UserFavorite.created_at.desc())
            .all()
        ]
    if favorites_only:
        return favorites[:25]

    mini_tickers = build_scan_universe(services.kronos, cap=25)
    sector_tickers: list[str] = []
    if sector:
        from app.sec.db_models import SecCompanyMapping

        sector_tickers = [
            row.ticker
            for row in session.query(SecCompanyMapping).filter(SecCompanyMapping.sector.isnot(None)).all()
            if sector_matches(row.sector, sector)
        ]
    ordered = list(dict.fromkeys(favorites + sector_tickers + mini_tickers))
    return ordered[:25]


def _path_bias_from_change(change: float | None) -> str | None:
    if change is None:
        return None
    if change > 0.002:
        return "bullish"
    if change < -0.002:
        return "bearish"
    return "flat"


def _enrich_ticker(services: Services, ticker: str, acc_row: dict[str, Any] | None) -> dict[str, Any]:
    components = (acc_row or {}).get("components") or {}
    why_parts: list[str] = []
    candidate: dict[str, Any] = {
        "ticker": ticker.upper(),
        "accumulation_score": (acc_row or {}).get("score"),
        "signal": (acc_row or {}).get("classification"),
        "components": components,
        "model_stance": None,
        "model_probability": None,
        "chart_path_bias": None,
        "path_change": None,
    }

    prediction = getattr(services, "prediction", None)
    if prediction is not None:
        try:
            pred = prediction.predict(ticker, horizon="5d")
            candidate["model_stance"] = pred.get("signal")
            candidate["model_probability"] = pred.get("probability")
            if pred.get("signal"):
                why_parts.append(f"Model stance {pred.get('signal')} at P(up) {float(pred.get('probability') or 0):.0%}")
        except Exception as exc:
            logger.info("research_prediction_failed", extra={"ticker": ticker, "error_type": type(exc).__name__})

    try:
        forecast = services.kronos.forecast(
            ticker,
            "long",
            "1Day",
            None,
            None,
            None,
            True,
            False,
            "kronos",
        )
        trend = forecast.get("trend") or {}
        change = trend.get("net_forecast_change")
        if change is None:
            change = trend.get("forecast_change")
        try:
            change_f = float(change) if change is not None else None
        except (TypeError, ValueError):
            change_f = None
        bias = _path_bias_from_change(change_f)
        # Map Kronos trend direction if bias missing
        if bias is None:
            direction = str(trend.get("direction") or "").lower()
            if direction in {"up", "bullish"}:
                bias = "bullish"
            elif direction in {"down", "bearish"}:
                bias = "bearish"
            elif direction:
                bias = "flat"
        candidate["chart_path_bias"] = bias
        candidate["path_change"] = change_f
        if bias:
            why_parts.append(f"Chart path bias {bias}")
    except Exception as exc:
        logger.info("research_forecast_failed", extra={"ticker": ticker, "error_type": type(exc).__name__})

    if components.get("institutional", 0) >= 60:
        why_parts.append("Institutional: Accumulating")
    if components.get("insider", 0) >= 55:
        why_parts.append("Insiders: Moderately positive")
    candidate["why"] = "; ".join(why_parts) if why_parts else "Limited forecast/SEC context"
    return candidate


def _rank_key(item: dict[str, Any]) -> tuple[float, float, float]:
    probability = item.get("model_probability")
    try:
        p = float(probability) if probability is not None else -1.0
    except (TypeError, ValueError):
        p = -1.0
    path_change = item.get("path_change")
    try:
        path = float(path_change) if path_change is not None else -1.0
    except (TypeError, ValueError):
        path = -1.0
    score = item.get("accumulation_score")
    try:
        acc = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        acc = 0.0
    return (p, path, acc)


async def run_research_query(
    query: str,
    session: Session,
    services: Services,
    *,
    user: Any | None = None,
) -> dict[str, Any]:
    parsed = parse_research_query(query)
    filters = parsed["filters"]
    sector = parsed.get("sector")
    favorites_only = bool(filters.get("favorites_only"))

    universe = _candidate_universe(
        session,
        services,
        sector=sector,
        user=user,
        favorites_only=favorites_only,
    )
    services.sec.maybe_auto_scan(session, services)
    if universe:
        await services.sec.mini_scan(services, universe, cap=min(25, len(universe)))

    acc_rows = services.sec.top_accumulation(session, sector=sector, min_score=0.0, limit=50)
    acc_by_ticker = {str(row.get("ticker", "")).upper(): row for row in acc_rows}

    # Prefer enriching favorites first, then remaining universe
    enrich_list = universe[:FORECAST_ENRICH_CAP]
    if not enrich_list and acc_rows:
        enrich_list = [str(row["ticker"]).upper() for row in acc_rows[:FORECAST_ENRICH_CAP]]

    candidates: list[dict[str, Any]] = []
    fallback = False
    for ticker in enrich_list:
        try:
            candidates.append(_enrich_ticker(services, ticker, acc_by_ticker.get(ticker.upper())))
        except Exception:
            fallback = True
            logger.exception("research_enrich_failed", extra={"ticker": ticker})

    candidates.sort(key=_rank_key, reverse=True)
    if filters.get("signal") == "DISTRIBUTION":
        candidates = [
            item
            for item in candidates
            if str(item.get("model_stance") or "").upper().find("SELL") >= 0
            or str(item.get("chart_path_bias") or "") == "bearish"
        ] or candidates
    elif filters.get("signal") == "ACCUMULATION":
        candidates = [
            item
            for item in candidates
            if str(item.get("model_stance") or "").upper().find("BUY") >= 0
            or str(item.get("chart_path_bias") or "") == "bullish"
        ] or candidates

    structured = {"query": query, "filters": filters, "candidates": candidates, "fallback": fallback}
    narrative = await _llm_narrative(services.settings, structured, user=user)
    if not narrative:
        narrative = _template_narrative(query, candidates, filters, fallback=fallback)
    return {
        "query": query,
        "filters": filters,
        "candidates": candidates,
        "narrative": narrative,
        "disclaimer": DISCLAIMER,
    }
