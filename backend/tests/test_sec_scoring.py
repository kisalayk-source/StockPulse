from app.sec.config_loader import load_sec_config
from app.sec.engines.accumulation import compute_accumulation_score, signal_from_score
from app.sec.models import NormalizedEvent
from app.sec.normalization import utc_now


def test_score_bounds() -> None:
    config = load_sec_config("backend/configs/sec_accumulation.yaml")
    events = [
        NormalizedEvent(
            event_id="1",
            source="13F",
            accession_number="A1",
            filing_date=None,
            reporting_period=None,
            event_type="INCREASED",
            component="institutional",
            signal_label="Reported institutional position change",
            data_timestamp=utc_now(),
            ticker="XOM",
            polarity=0.7,
        )
    ]
    payload = compute_accumulation_score(events, [], {}, config)
    assert 0 <= payload["score"] <= 100


def test_signal_mapping() -> None:
    assert signal_from_score(85) == "ACCUMULATION"
    assert signal_from_score(45) == "NEUTRAL"
    assert signal_from_score(15) == "DISTRIBUTION"


def test_missing_data_renormalizes() -> None:
    config = load_sec_config("backend/configs/sec_accumulation.yaml")
    payload = compute_accumulation_score([], [], {}, config)
    assert payload["score"] == 50.0
