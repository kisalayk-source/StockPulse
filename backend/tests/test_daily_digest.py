from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.content.daily_digest import stories_for_day
from app.content.voiceover import chart_png, voiceover_script, write_story_assets
from app.db import Base
from app.government.db_models import GovernmentEvent
from app.sec.db_models import InsiderTransaction


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_digest_returns_top_five_by_dollar_value() -> None:
    day = date(2026, 9, 24)
    stamp = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
    session = _session()
    session.add_all(
        [
            InsiderTransaction(
                accession_number="ins-1",
                insider_name="Ada Lovelace",
                insider_title="CEO",
                issuer_ticker="AAA",
                transaction_date=day,
                filing_date=day,
                transaction_code="P",
                normalized_type="DISCRETIONARY_BUY",
                shares=1000,
                price=10,
                value=5_000_000,
            ),
            InsiderTransaction(
                accession_number="ins-2",
                insider_name="Grace Hopper",
                insider_title="Director",
                issuer_ticker="BBB",
                transaction_date=day,
                filing_date=day,
                transaction_code="S",
                normalized_type="DISCRETIONARY_SELL",
                shares=10,
                price=2,
                value=20,
            ),
            GovernmentEvent(
                source="sam",
                event_id="award-1",
                event_type="award",
                company_name="Lockheed",
                ticker="LMT",
                agency="DOD",
                title="Missile support",
                awarded_amount=2_000_000_000,
                event_at=stamp,
            ),
            GovernmentEvent(
                source="sam",
                event_id="award-old",
                event_type="award",
                company_name="Old Co",
                ticker="OLD",
                agency="NASA",
                title="Yesterday",
                awarded_amount=9_000_000_000,
                event_at=datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc),
            ),
            GovernmentEvent(
                source="sam",
                event_id="award-midnight",
                event_type="award",
                company_name="Raytheon",
                ticker="RTX",
                agency="DOD",
                title="Radar support",
                awarded_amount=50_000_000,
                event_at=datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc),
            ),
            InsiderTransaction(
                accession_number="ins-empty",
                insider_name="Empty Filing",
                issuer_ticker="VZ",
                filing_date=day,
                transaction_date=None,
                transaction_code="A",
                normalized_type="COMPENSATION",
                shares=0,
                price=None,
                value=None,
            ),
        ]
    )
    for index in range(4):
        session.add(
            InsiderTransaction(
                accession_number=f"ins-extra-{index}",
                insider_name=f"Buyer {index}",
                issuer_ticker=f"T{index}",
                filing_date=day,
                transaction_date=day,
                transaction_code="P",
                normalized_type="DISCRETIONARY_BUY",
                shares=1,
                price=1,
                value=1_000_000 + index,
            )
        )
    session.commit()

    stories = stories_for_day(session, day)
    session.close()

    assert len(stories) == 5
    assert stories[0]["kind"] == "contract"
    assert stories[0]["ticker"] == "LMT"
    assert [story["rank"] for story in stories] == [1, 2, 3, 4, 5]
    assert all(story["ticker"] != "OLD" for story in stories)
    assert any(story["ticker"] == "RTX" for story in stories)
    assert stories[0]["value"] > stories[1]["value"]
    assert all(story.get("amount_reason") is None for story in stories if story["value"] > 0)


def test_zero_amount_story_explains_why() -> None:
    day = date(2026, 9, 28)
    session = _session()
    session.add_all(
        [
            InsiderTransaction(
                accession_number="ins-empty",
                insider_name="Empty Filing",
                issuer_ticker="VZ",
                filing_date=day,
                transaction_date=None,
                transaction_code="A",
                normalized_type="COMPENSATION",
                shares=0,
                price=None,
                value=None,
            ),
            GovernmentEvent(
                source="sam",
                event_id="award-blank",
                event_type="award",
                company_name="Blank Co",
                ticker="BLK",
                agency="GSA",
                title="Support services",
                event_at=datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()
    stories = stories_for_day(session, day)
    session.close()

    assert len(stories) == 2
    by_ticker = {story["ticker"]: story for story in stories}
    assert by_ticker["VZ"]["value"] == 0
    assert by_ticker["VZ"]["amount_reason"] == (
        "No dollar amount reported; compensation award with no share count or price"
    )
    assert "$0" not in by_ticker["VZ"]["summary"]
    assert "compensation award with no share count or price" in by_ticker["VZ"]["summary"]
    assert by_ticker["BLK"]["value"] == 0
    assert "no awarded, obligated, ceiling, or estimated value" in (by_ticker["BLK"]["amount_reason"] or "")
    assert "$0" not in by_ticker["BLK"]["summary"]


def test_voiceover_is_faceless_and_chart_is_png(tmp_path: Path) -> None:
    story = {
        "rank": 1,
        "kind": "contract",
        "ticker": "LMT",
        "title": "DOD awarded Lockheed",
        "summary": "Lockheed received Missile support from DOD. The reported amount is $2.0B.",
        "value": 2_000_000_000,
        "actor": "Lockheed",
        "happened_on": "2026-09-24",
        "source_url": None,
    }
    script = voiceover_script(story)
    assert script.startswith("HOOK\n")
    assert "I " not in script
    assert "billion dollars" in script
    assert "not investment advice" in script
    png = chart_png(story)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    paths = write_story_assets(story, tmp_path / "01-lmt-contract")
    assert Path(paths["script"]).read_text(encoding="utf-8").startswith("HOOK\n")
    assert Path(paths["chart"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
