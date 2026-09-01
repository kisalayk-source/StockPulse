from datetime import date
from pathlib import Path

import pytest

from app.config import Settings
from app.db import init_db, reset_db_state
from app.sec.service import SecService


@pytest.fixture
def session():
    settings = Settings(database_url="sqlite:///:memory:")
    init_db(settings)
    from app.db import get_session

    gen = get_session()
    db = next(gen)
    try:
        yield db
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
        reset_db_state()


def test_amendment_supersedes_prior(session) -> None:
    service = SecService(Settings(sec_enabled=False))
    fixture = Path(__file__).parent / "fixtures" / "sec" / "form_13f_infotable.xml"
    xml_text = fixture.read_text(encoding="utf-8")
    service.ingest_fixture_filing(
        session,
        "XOM",
        {
            "accession_number": "0001-001",
            "form_type": "13F-HR",
            "form_family": "13F",
            "filing_date": date(2024, 3, 1),
            "report_period": date(2023, 12, 31),
            "cik": "0000034088",
        },
        xml_text,
    )
    service.ingest_fixture_filing(
        session,
        "XOM",
        {
            "accession_number": "0001-002",
            "form_type": "13F-HR/A",
            "form_family": "13F",
            "filing_date": date(2024, 4, 1),
            "report_period": date(2023, 12, 31),
            "is_amendment": True,
            "cik": "0000034088",
        },
        xml_text,
    )
    from app.sec.db_models import SecFiling

    prior = session.query(SecFiling).filter(SecFiling.accession_number == "0001-001").one()
    assert prior.superseded is True


def test_duplicate_form4_ignored(session) -> None:
    service = SecService(Settings(sec_enabled=False))
    xml_text = (Path(__file__).parent / "fixtures" / "sec" / "form_4.xml").read_text(encoding="utf-8")
    meta = {
        "accession_number": "0004-001",
        "form_type": "4",
        "form_family": "4",
        "filing_date": date(2024, 5, 16),
        "cik": "0000034088",
    }
    service.ingest_fixture_filing(session, "XOM", meta, xml_text)
    service.ingest_fixture_filing(session, "XOM", meta, xml_text)
    from app.sec.db_models import InsiderTransaction

    assert session.query(InsiderTransaction).count() == 2


def test_ingest_filing_serializes_date_metadata(session) -> None:
    import asyncio

    from app.sec.db_models import SecFiling

    service = SecService(Settings(sec_enabled=False))
    filing_meta = {
        "form_type": "4",
        "accession_number": "0001-date-test",
        "filing_date": date(2026, 8, 27),
        "report_period": date(2026, 8, 25),
        "is_amendment": False,
        "form_family": "4",
    }

    async def run() -> None:
        await service.ingest_filing(session, "0000320193", "AAPL", filing_meta)

    asyncio.run(run())
    row = session.query(SecFiling).filter(SecFiling.accession_number == "0001-date-test").one()
    assert row.ticker == "AAPL"
    assert row.filing_date == date(2026, 8, 27)
    assert row.raw_metadata is not None
    assert "2026-08-27" in row.raw_metadata
