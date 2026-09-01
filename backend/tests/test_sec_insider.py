from datetime import date, timedelta

from app.sec.engines.insider import score_insider
from app.sec.models import NormalizedEvent
from app.sec.normalization import utc_now


def _event(event_type: str, name: str, title: str, days_ago: int) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"test:{name}:{days_ago}",
        source="Form4",
        accession_number="0001",
        filing_date=date.today() - timedelta(days=days_ago),
        reporting_period=date.today() - timedelta(days=days_ago),
        event_type=event_type,
        component="insider",
        signal_label="Insider transaction filing",
        data_timestamp=utc_now(),
        ticker="XOM",
        polarity=1.0 if "BUY" in event_type else -1.0,
        metadata={"insider_name": name, "insider_title": title, "value": 100000.0},
    )


def test_cluster_buy_detection() -> None:
    config = {"insider_cluster": {"window_days": 30, "min_insiders": 3}}
    events = [
        _event("DISCRETIONARY_BUY", "A", "CEO", 1),
        _event("DISCRETIONARY_BUY", "B", "CFO", 2),
        _event("DISCRETIONARY_BUY", "C", "Director", 3),
    ]
    score, evidence = score_insider(events, config)
    assert score >= 60
    assert any("cluster buy" in item.lower() for item in evidence)


def test_compensation_not_cluster_sell() -> None:
    config = {"insider_cluster": {"window_days": 30, "min_insiders": 3}}
    events = [_event("COMPENSATION", f"Person {idx}", "Officer", idx) for idx in range(3)]
    _, evidence = score_insider(events, config)
    assert not any("cluster sell" in item.lower() for item in evidence)
