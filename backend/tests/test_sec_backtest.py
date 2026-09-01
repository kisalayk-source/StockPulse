from datetime import date

from app.sec.backtest.runner import filings_available_as_of, run_accumulation_backtest


def test_no_future_filings(session) -> None:
    from app.sec.db_models import SecFiling

    session.add(
        SecFiling(
            accession_number="0001",
            cik="0000034088",
            ticker="XOM",
            form_type="13F-HR",
            form_family="13F",
            filing_date=date(2024, 6, 1),
        )
    )
    session.flush()
    assert filings_available_as_of(session, "XOM", date(2024, 5, 1)) is False
    assert filings_available_as_of(session, "XOM", date(2024, 6, 2)) is True


def test_backtest_summary(session) -> None:
    bars = [
        {"timestamp": f"2024-01-{(idx % 28) + 1:02d}T00:00:00+00:00", "close": 100 + idx}
        for idx in range(300)
    ]
    payload = run_accumulation_backtest(session, "XOM", bars, [date(2024, 1, 15), date(2024, 2, 15)])
    assert "summary" in payload


import pytest
from app.config import Settings
from app.db import init_db, reset_db_state


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
