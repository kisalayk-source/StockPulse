"""Top insider and contract stories for one calendar day."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.government.db_models import GovernmentEvent
from app.sec.db_models import InsiderTransaction
from app.sec.normalization import INSIDER_ACTION_LABELS

STORY_LIMIT = 5
DIGEST_ZONE = ZoneInfo("America/Los_Angeles")


def digest_today() -> date:
    return datetime.now(DIGEST_ZONE).date()


def stories_for_day(session: Session, day: date, *, limit: int = STORY_LIMIT) -> list[dict[str, Any]]:
    ranked = [*_insider_stories(session, day), *_contract_stories(session, day)]
    ranked.sort(key=lambda story: float(story["value"]), reverse=True)
    stories = ranked[:limit]
    for index, story in enumerate(stories, start=1):
        story["rank"] = index
    return stories


def digest_payload(session: Session, day: date | None = None) -> dict[str, Any]:
    selected = day or digest_today()
    stories = stories_for_day(session, selected)
    return {
        "date": selected.isoformat(),
        "timezone": "America/Los_Angeles",
        "count": len(stories),
        "stories": stories,
    }


def _insider_stories(session: Session, day: date) -> list[dict[str, Any]]:
    rows = (
        session.query(InsiderTransaction)
        .filter(InsiderTransaction.filing_date == day)
        .all()
    )
    stories: list[dict[str, Any]] = []
    for row in rows:
        value = _insider_value(row)
        amount_reason = _insider_amount_reason(row) if value <= 0 else None
        ticker = (row.issuer_ticker or "").upper() or None
        name = row.insider_name or "An insider"
        action = _insider_action_verb(row.normalized_type)
        title = f"{name} {action} {ticker or 'shares'}"
        shares = abs(float(row.shares or 0))
        price = f"${float(row.price):.2f}" if row.price else None
        if amount_reason:
            if shares > 0 and price:
                detail = f"{action} {_compact_number(shares)} shares of {ticker or 'the issuer'} at {price}"
            elif shares > 0:
                detail = f"{action} {_compact_number(shares)} shares of {ticker or 'the issuer'}"
            else:
                detail = f"{action} {ticker or 'shares'}"
            summary = (
                f"{name}, {row.insider_title or 'an insider'}, {detail}. {amount_reason}."
            )
        else:
            summary = (
                f"{name}, {row.insider_title or 'an insider'}, {action} "
                f"{_compact_number(shares)} shares of {ticker or 'the issuer'} at "
                f"{price or 'an unlisted price'}. The reported value is {_compact_money(value)}."
            )
        stories.append(
            {
                "rank": 0,
                "kind": "insider",
                "ticker": ticker,
                "title": title,
                "summary": summary,
                "value": value,
                "amount_reason": amount_reason,
                "actor": name,
                "happened_on": day.isoformat(),
                "source_url": None,
            }
        )
    return stories


def _contract_stories(session: Session, day: date) -> list[dict[str, Any]]:
    start, end = _day_bounds(day)
    rows = (
        session.query(GovernmentEvent)
        .filter(
            or_(
                and_(GovernmentEvent.event_at >= start, GovernmentEvent.event_at < end),
                and_(GovernmentEvent.award_date >= start, GovernmentEvent.award_date < end),
                and_(GovernmentEvent.published_at >= start, GovernmentEvent.published_at < end),
            )
        )
        .all()
    )
    stories: list[dict[str, Any]] = []
    for row in rows:
        if not any(_stamp_on_day(stamp, day) for stamp in (row.event_at, row.award_date, row.published_at)):
            continue
        value = _contract_value(row)
        amount_reason = _contract_amount_reason(row) if value <= 0 else None
        ticker = (row.ticker or "").upper() or None
        company = row.company_name or ticker or "A contractor"
        agency = row.agency or "a federal agency"
        headline = row.title or "a government contract"
        title = f"{agency} awarded {company}"
        if amount_reason:
            summary = f"{company} received {headline} from {agency}. {amount_reason}."
        else:
            summary = (
                f"{company} received {headline} from {agency}. "
                f"The reported amount is {_compact_money(value)}."
            )
        stories.append(
            {
                "rank": 0,
                "kind": "contract",
                "ticker": ticker,
                "title": title,
                "summary": summary,
                "value": value,
                "amount_reason": amount_reason,
                "actor": company,
                "happened_on": day.isoformat(),
                "source_url": row.source_url,
            }
        )
    return stories


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    # Date-only awards are stored as UTC midnight. That instant is the previous
    # evening in Pacific time, so the window starts at UTC midnight of this day.
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=DIGEST_ZONE)
    return start, end


def _stamp_on_day(stamp: datetime | None, day: date) -> bool:
    if stamp is None:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    utc = stamp.astimezone(timezone.utc)
    if utc.hour == utc.minute == utc.second == utc.microsecond == 0:
        return utc.date() == day
    return utc.astimezone(DIGEST_ZONE).date() == day


def _insider_value(row: InsiderTransaction) -> float:
    if row.value:
        return abs(float(row.value))
    if row.price and row.shares:
        return abs(float(row.price) * float(row.shares))
    return 0.0


def _contract_value(row: GovernmentEvent) -> float:
    for amount in (row.awarded_amount, row.obligated_amount, row.ceiling_amount, row.estimated_value, row.transaction_amount):
        if amount:
            return abs(float(amount))
    return 0.0


def _insider_action_verb(normalized_type: str | None) -> str:
    label = INSIDER_ACTION_LABELS.get(normalized_type or "", "Other transaction").lower()
    if normalized_type == "DISCRETIONARY_BUY":
        return "bought"
    if normalized_type == "DISCRETIONARY_SELL":
        return "sold"
    if normalized_type == "COMPENSATION":
        return "was awarded"
    if normalized_type == "OPTION_EXERCISE":
        return "exercised options in"
    if normalized_type == "TAX_WITHHOLDING":
        return "had shares withheld from"
    return label


def _insider_amount_reason(row: InsiderTransaction) -> str:
    shares = abs(float(row.shares or 0))
    has_price = row.price is not None and float(row.price) > 0
    normalized = row.normalized_type or ""
    if normalized == "COMPENSATION" and shares <= 0 and not has_price:
        return "No dollar amount reported; compensation award with no share count or price"
    if shares <= 0 and not has_price:
        return "No dollar amount reported; filing has no share count or price"
    if shares > 0 and not has_price:
        return "No dollar amount reported; share count is listed without a price"
    if shares <= 0 and has_price:
        return "No dollar amount reported; price is listed without a share count"
    if row.value is not None and abs(float(row.value)) == 0:
        return "Filing reports a $0 transaction value"
    return "No dollar amount reported in the filing"


def _contract_amount_reason(row: GovernmentEvent) -> str:
    amounts = (
        row.awarded_amount,
        row.obligated_amount,
        row.ceiling_amount,
        row.estimated_value,
        row.transaction_amount,
    )
    if all(amount is None for amount in amounts):
        return "No dollar amount reported; award has no awarded, obligated, ceiling, or estimated value"
    return "No dollar amount reported; available contract amounts are zero"


def _compact_number(value: float) -> str:
    return _compact_money(value).lstrip("$")


def _compact_money(value: float) -> str:
    amount = abs(float(value))
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:.0f}"
