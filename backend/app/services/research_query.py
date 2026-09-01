from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.dependencies import Services
from app.sec.scan import build_scan_universe
from app.sec.sectors import normalize_sector

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
    "Research output combines SEC accumulation signals, fundamentals, and model data. "
    "It is not investment advice or a trading instruction."
)


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
            "Try a broader sector or wait for the market scan to finish."
        )
    lines = ["Top candidates", ""]
    if fallback:
        lines.append("Showing best available matches from the current score cache.")
        lines.append("")
    for idx, item in enumerate(candidates[:5], start=1):
        lines.append(
            f"{idx}. {item['ticker']}\n"
            f"   Accumulation Score: {item.get('accumulation_score', 'n/a')}\n"
            f"   Signal: {item.get('signal', 'n/a')}"
        )
        if item.get("why"):
            lines.append(f"   Why: {item['why']}")
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


async def _llm_narrative(settings, structured: dict[str, Any]) -> str | None:
    from app.services.openai_client import call_openai_chat

    system_prompt = (
        "You explain stock research using ONLY the JSON context provided. "
        "Never invent tickers, scores, or filings. "
        "Cite evidence from the context. Include that this is a research signal, not trading advice."
    )
    return await call_openai_chat(
        settings,
        system_prompt=system_prompt,
        user_content=f"Query: {structured['query']}\nContext:\n{json.dumps(structured, indent=2)}",
        temperature=0.2,
        log_key="research_llm_failed",
    )


def _build_candidates(
    rows: list[dict[str, Any]],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        components = row.get("components") or {}
        if filters.get("insider_accumulation") == "positive" and components.get("insider", 50) < 50:
            continue
        why_parts = []
        if components.get("institutional", 0) >= 60:
            why_parts.append("Institutional: Accumulating")
        if components.get("insider", 0) >= 55:
            why_parts.append("Insiders: Moderately positive")
        if components.get("fundamentals", 0) >= 60:
            why_parts.append("Fundamentals: Strong")
        candidates.append(
            {
                "ticker": row["ticker"],
                "accumulation_score": row["score"],
                "signal": row.get("classification"),
                "components": components,
                "why": "; ".join(why_parts) if why_parts else "Mixed SEC signals",
            }
        )
    return candidates


async def run_research_query(query: str, session: Session, services: Services) -> dict[str, Any]:
    parsed = parse_research_query(query)
    filters = parsed["filters"]
    sector = parsed.get("sector")

    mini_tickers = build_scan_universe(services.kronos, cap=25)
    if sector:
        from app.sec.db_models import SecCompanyMapping
        from app.sec.sectors import sector_matches

        sector_tickers = [
            row.ticker
            for row in session.query(SecCompanyMapping).filter(SecCompanyMapping.sector.isnot(None)).all()
            if sector_matches(row.sector, sector)
        ]
        mini_tickers = list(dict.fromkeys(sector_tickers + mini_tickers))[:25]
    services.sec.maybe_auto_scan(session, services)
    await services.sec.mini_scan(services, mini_tickers, cap=25)

    min_score = 55.0 if filters.get("institutional_accumulation") == "strong" else 45.0
    rows = services.sec.top_accumulation(session, sector=sector, min_score=min_score, limit=10)
    candidates = _build_candidates(rows, filters)
    fallback = False
    if not candidates:
        fallback = True
        rows = services.sec.top_accumulation(session, sector=sector, min_score=0.0, limit=10)
        candidates = _build_candidates(rows, {k: v for k, v in filters.items() if k != "insider_accumulation"})

    structured = {"query": query, "filters": filters, "candidates": candidates, "fallback": fallback}
    narrative = await _llm_narrative(services.settings, structured)
    if not narrative:
        narrative = _template_narrative(query, candidates, filters, fallback=fallback)
    return {
        "query": query,
        "filters": filters,
        "candidates": candidates,
        "narrative": narrative,
        "disclaimer": DISCLAIMER,
    }

