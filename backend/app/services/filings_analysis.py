from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.dependencies import Services
from app.sec.db_models import (
    AccumulationScore,
    BeneficialOwnership,
    InsiderTransaction,
    InstitutionalPositionChange,
    SecFiling,
)
from app.sec.normalization import polarity_for_insider

DISCLAIMER = (
    "SEC filing analysis combines structured filing data and accumulation signals. "
    "It is not investment advice or a trading instruction."
)

SENTIMENT_LABELS = {
    "good": "Good news",
    "bad": "Bad news",
    "mixed": "Mixed signals",
    "neutral": "Neutral",
}


def _build_context(session: Session, ticker: str, months: int) -> dict[str, Any]:
    symbol = ticker.upper()
    cutoff = date.today() - timedelta(days=max(1, months) * 30)

    filings = (
        session.query(SecFiling)
        .filter(SecFiling.ticker == symbol, SecFiling.filing_date >= cutoff)
        .order_by(SecFiling.filing_date.desc())
        .limit(100)
        .all()
    )
    summary: dict[str, int] = {"13F": 0, "13D": 0, "13G": 0, "4": 0}
    amendment_count = 0
    for filing in filings:
        if filing.form_family in summary:
            summary[filing.form_family] += 1
        if filing.is_amendment:
            amendment_count += 1

    insider_rows = (
        session.query(InsiderTransaction)
        .filter(InsiderTransaction.issuer_ticker == symbol)
        .filter(InsiderTransaction.filing_date >= cutoff)
        .order_by(InsiderTransaction.filing_date.desc())
        .limit(20)
        .all()
    )
    insider_transactions = [
        {
            "insider": row.insider_name,
            "title": row.insider_title,
            "transaction_date": row.transaction_date.isoformat() if row.transaction_date else None,
            "filing_date": row.filing_date.isoformat() if row.filing_date else None,
            "normalized_type": row.normalized_type,
            "shares": row.shares,
            "value": row.value,
        }
        for row in insider_rows
    ]

    ownership_rows = (
        session.query(BeneficialOwnership)
        .filter(BeneficialOwnership.issuer_ticker == symbol)
        .filter(BeneficialOwnership.filing_date >= cutoff)
        .order_by(BeneficialOwnership.filing_date.desc())
        .limit(20)
        .all()
    )
    beneficial_ownership = [
        {
            "reporter": row.reporter_name,
            "form_type": row.form_type,
            "filing_date": row.filing_date.isoformat() if row.filing_date else None,
            "ownership_pct": row.ownership_pct,
            "passive": row.passive_flag,
            "event_type": row.event_type,
        }
        for row in ownership_rows
    ]

    institutional_changes = (
        session.query(InstitutionalPositionChange)
        .filter(InstitutionalPositionChange.issuer_ticker == symbol)
        .order_by(InstitutionalPositionChange.report_period.desc())
        .limit(10)
        .all()
    )
    institutional = [
        {
            "manager": row.manager_name,
            "classification": row.classification,
            "change_pct": row.change_pct,
            "reporting_period": row.report_period.isoformat() if row.report_period else None,
        }
        for row in institutional_changes
    ]

    score_row = (
        session.query(AccumulationScore)
        .filter(AccumulationScore.ticker == symbol)
        .order_by(AccumulationScore.score_date.desc())
        .first()
    )
    accumulation = None
    if score_row:
        accumulation = {
            "score": score_row.score,
            "signal": score_row.signal,
            "classification": score_row.classification,
            "components": json.loads(score_row.components_json),
        }

    return {
        "ticker": symbol,
        "months": months,
        "cutoff_date": cutoff.isoformat(),
        "summary": summary,
        "filing_count": len(filings),
        "amendment_count": amendment_count,
        "insider_transactions": insider_transactions,
        "beneficial_ownership": beneficial_ownership,
        "institutional_changes": institutional,
        "accumulation": accumulation,
    }


def _score_insider_activity(transactions: list[dict[str, Any]]) -> float:
    total = 0.0
    for txn in transactions:
        total += polarity_for_insider(str(txn.get("normalized_type", "")))
    return total


def _rule_based_analysis(context: dict[str, Any]) -> dict[str, Any]:
    symbol = context["ticker"]
    summary = context["summary"]
    insider_score = _score_insider_activity(context["insider_transactions"])
    buys = sum(1 for t in context["insider_transactions"] if t.get("normalized_type") == "DISCRETIONARY_BUY")
    sells = sum(1 for t in context["insider_transactions"] if t.get("normalized_type") == "DISCRETIONARY_SELL")
    active_13d = sum(1 for o in context["beneficial_ownership"] if "13D" in str(o.get("form_type", "")))
    passive_13g = sum(1 for o in context["beneficial_ownership"] if "13G" in str(o.get("form_type", "")))
    inst_increasing = sum(
        1 for c in context["institutional_changes"]
        if c.get("classification") in {"NEW_POSITION", "INCREASED"}
    )
    inst_decreasing = sum(
        1 for c in context["institutional_changes"]
        if c.get("classification") in {"DECREASED", "EXITED"}
    )

    highlights: list[dict[str, str]] = []
    gist: list[str] = []
    score_signals: list[float] = []

    total_filings = context["filing_count"]
    if total_filings == 0:
        return {
            "headline": f"No SEC filings found for {symbol} in the last {context['months']} months.",
            "gist": ["No recent Form 4, 13F, 13D, or 13G filings on record."],
            "sentiment": "neutral",
            "highlights": [],
        }

    gist.append(
        f"{total_filings} filing(s) since {context['cutoff_date']}: "
        f"{summary.get('4', 0)} Form 4, {summary.get('13F', 0)} 13F, "
        f"{summary.get('13D', 0)} 13D, {summary.get('13G', 0)} 13G."
    )

    if buys > sells:
        gist.append(f"Insider activity skews positive: {buys} discretionary buy(s) vs {sells} sell(s).")
        highlights.append({"category": "insider", "text": f"{buys} insider buy(s) vs {sells} sell(s)", "tone": "positive"})
        score_signals.append(0.5)
    elif sells > buys:
        gist.append(f"Insider activity skews negative: {sells} discretionary sell(s) vs {buys} buy(s).")
        highlights.append({"category": "insider", "text": f"{sells} insider sell(s) vs {buys} buy(s)", "tone": "negative"})
        score_signals.append(-0.5)
    elif buys or sells:
        gist.append(f"Mixed insider activity: {buys} buy(s) and {sells} sell(s).")
        highlights.append({"category": "insider", "text": "Mixed insider buy/sell activity", "tone": "neutral"})

    if insider_score > 0:
        score_signals.append(insider_score / max(buys + sells, 1))
    elif insider_score < 0:
        score_signals.append(insider_score / max(buys + sells, 1))

    if active_13d:
        gist.append(f"{active_13d} active beneficial ownership filing(s) (13D) — potential activist interest.")
        highlights.append({"category": "ownership", "text": f"{active_13d} active 13D filing(s)", "tone": "neutral"})
    if passive_13g:
        highlights.append({"category": "ownership", "text": f"{passive_13g} passive 13G filing(s)", "tone": "neutral"})

    if inst_increasing > inst_decreasing:
        gist.append(f"Institutional positions trending up: {inst_increasing} increase(s) vs {inst_decreasing} decrease(s).")
        highlights.append({"category": "institutional", "text": "Institutional positions increasing", "tone": "positive"})
        score_signals.append(0.4)
    elif inst_decreasing > inst_increasing:
        gist.append(f"Institutional positions trending down: {inst_decreasing} decrease(s) vs {inst_increasing} increase(s).")
        highlights.append({"category": "institutional", "text": "Institutional positions decreasing", "tone": "negative"})
        score_signals.append(-0.4)

    accumulation = context.get("accumulation")
    if accumulation:
        acc_score = accumulation["score"]
        gist.append(
            f"Accumulation score: {acc_score:.0f}/100 ({accumulation['classification'].replace('_', ' ').lower()})."
        )
        if acc_score >= 60:
            score_signals.append(0.6)
            highlights.append({"category": "filings", "text": f"Strong accumulation score ({acc_score:.0f})", "tone": "positive"})
        elif acc_score <= 40:
            score_signals.append(-0.6)
            highlights.append({"category": "filings", "text": f"Weak accumulation score ({acc_score:.0f})", "tone": "negative"})

    if context["amendment_count"]:
        highlights.append({
            "category": "filings",
            "text": f"{context['amendment_count']} amended filing(s)",
            "tone": "neutral",
        })

    avg_signal = sum(score_signals) / len(score_signals) if score_signals else 0.0
    if avg_signal >= 0.35:
        sentiment = "good"
        headline = f"Recent SEC activity for {symbol} looks mostly positive."
    elif avg_signal <= -0.35:
        sentiment = "bad"
        headline = f"Recent SEC activity for {symbol} raises caution flags."
    elif score_signals:
        sentiment = "mixed"
        headline = f"Recent SEC activity for {symbol} shows mixed signals."
    else:
        sentiment = "neutral"
        headline = f"Recent SEC activity for {symbol} is limited or neutral."

    return {
        "headline": headline,
        "gist": gist[:5],
        "sentiment": sentiment,
        "highlights": highlights[:6],
    }


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    sentiment = str(parsed.get("sentiment", "neutral")).lower()
    if sentiment not in SENTIMENT_LABELS:
        sentiment = "neutral"
    gist = parsed.get("gist")
    if not isinstance(gist, list):
        gist = [str(parsed.get("gist", ""))] if parsed.get("gist") else []
    gist = [str(item) for item in gist if item][:5]
    highlights = parsed.get("highlights")
    if not isinstance(highlights, list):
        highlights = []
    normalized_highlights = []
    for item in highlights[:6]:
        if not isinstance(item, dict):
            continue
        tone = str(item.get("tone", "neutral")).lower()
        if tone not in {"positive", "negative", "neutral"}:
            tone = "neutral"
        normalized_highlights.append({
            "category": str(item.get("category", "filings")),
            "text": str(item.get("text", "")),
            "tone": tone,
        })
    headline = str(parsed.get("headline", "")).strip()
    if not headline or not gist:
        return None
    return {
        "headline": headline,
        "gist": gist,
        "sentiment": sentiment,
        "highlights": normalized_highlights,
    }


async def _llm_analysis(settings: Any, context: dict[str, Any], user: Any | None = None) -> dict[str, Any] | None:
    from app.services.openai_client import call_openai_chat

    system_prompt = (
        "You analyze SEC filing activity for a single stock using ONLY the JSON context provided. "
        "Never invent filings, insiders, or scores. "
        "Return ONLY valid JSON with this schema:\n"
        '{"headline":"one-line takeaway","gist":["bullet"],"sentiment":"good|bad|mixed|neutral",'
        '"highlights":[{"category":"insider|institutional|ownership|filings","text":"...","tone":"positive|negative|neutral"}]}\n'
        "Sentiment guidance: good = net positive insider/institutional signals; "
        "bad = net negative; mixed = conflicting signals; neutral = insufficient or balanced activity. "
        "Include that this is research analysis, not trading advice, in the gist if relevant."
    )
    content = await call_openai_chat(
        settings,
        system_prompt=system_prompt,
        user_content=f"Analyze SEC filings for {context['ticker']}:\n{json.dumps(context, indent=2)}",
        temperature=0.2,
        log_key="filings_analysis_llm_failed",
        user=user,
    )
    if not content:
        return None
    return _parse_llm_json(content)


async def analyze_filings(
    session: Session,
    ticker: str,
    services: Services,
    *,
    months: int = 6,
    user: Any | None = None,
) -> dict[str, Any]:
    from app.services.openai_client import research_llm_active, research_llm_available

    context = _build_context(session, ticker, months)
    analysis = await _llm_analysis(services.settings, context, user=user)
    source = "llm"
    if not analysis:
        analysis = _rule_based_analysis(context)
        source = "rules"

    sentiment = analysis["sentiment"]
    return {
        "ticker": context["ticker"],
        "months": months,
        "headline": analysis["headline"],
        "gist": analysis["gist"],
        "sentiment": sentiment,
        "sentiment_label": SENTIMENT_LABELS.get(sentiment, "Neutral"),
        "highlights": analysis.get("highlights", []),
        "source": source,
        "llm_available": research_llm_available(services.settings),
        "llm_enabled": research_llm_active(services.settings, user),
        "disclaimer": DISCLAIMER,
    }
