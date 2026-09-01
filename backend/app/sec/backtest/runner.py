from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.sec.db_models import AccumulationScore, InstitutionalPositionChange, SecFiling


@dataclass
class BacktestBucket:
    name: str
    min_score: float
    max_score: float


BUCKETS = [
    BacktestBucket("high_accumulation", 80.0, 100.0),
    BacktestBucket("neutral", 40.0, 59.0),
    BacktestBucket("high_distribution", 0.0, 20.0),
]

HORIZONS = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}


def filings_available_as_of(session: Session, ticker: str, as_of: date) -> bool:
    """Ensure no filing dated after as_of is used."""
    future = (
        session.query(SecFiling)
        .filter(SecFiling.ticker == ticker.upper(), SecFiling.filing_date > as_of)
        .count()
    )
    return future == 0


def point_in_time_institutional_signal(session: Session, ticker: str, as_of: date) -> float:
    changes = (
        session.query(InstitutionalPositionChange)
        .join(SecFiling, SecFiling.accession_number == InstitutionalPositionChange.accession_number)
        .filter(
            InstitutionalPositionChange.issuer_ticker == ticker.upper(),
            SecFiling.filing_date <= as_of,
        )
        .all()
    )
    if not changes:
        return 50.0
    score = 50.0
    for change in changes:
        if change.classification in {"INCREASED", "NEW_POSITION"}:
            score += 5.0
        elif change.classification in {"DECREASED", "EXITED"}:
            score -= 5.0
    return max(0.0, min(100.0, score))


def forward_return(bars: list[dict[str, Any]], start_idx: int, horizon_bars: int) -> float | None:
    if start_idx < 0 or start_idx >= len(bars):
        return None
    end_idx = start_idx + horizon_bars
    if end_idx >= len(bars):
        return None
    start = float(bars[start_idx]["close"])
    end = float(bars[end_idx]["close"])
    if start <= 0:
        return None
    return (end - start) / start


def run_accumulation_backtest(
    session: Session,
    ticker: str,
    bars: list[dict[str, Any]],
    evaluation_dates: list[date],
) -> dict[str, Any]:
    """Compare forward returns by accumulation bucket without look-ahead bias."""
    results: dict[str, Any] = {bucket.name: {h: [] for h in HORIZONS} for bucket in BUCKETS}
    bar_dates = [date.fromisoformat(str(bar["timestamp"])[:10]) for bar in bars]
    for eval_date in evaluation_dates:
        if not filings_available_as_of(session, ticker, eval_date):
            continue
        score_row = (
            session.query(AccumulationScore)
            .filter(AccumulationScore.ticker == ticker.upper(), AccumulationScore.score_date <= eval_date)
            .order_by(AccumulationScore.score_date.desc())
            .first()
        )
        score = score_row.score if score_row else point_in_time_institutional_signal(session, ticker, eval_date)
        try:
            idx = next(i for i, d in enumerate(bar_dates) if d >= eval_date)
        except StopIteration:
            continue
        for bucket in BUCKETS:
            if bucket.min_score <= score <= bucket.max_score:
                for label, horizon in HORIZONS.items():
                    ret = forward_return(bars, idx, horizon)
                    if ret is not None:
                        results[bucket.name][label].append(ret)
                break
    summary: dict[str, Any] = {}
    for bucket in BUCKETS:
        summary[bucket.name] = {}
        for label, values in results[bucket.name].items():
            summary[bucket.name][label] = round(sum(values) / len(values), 4) if values else None
    return {"ticker": ticker.upper(), "summary": summary, "evaluation_points": len(evaluation_dates)}
