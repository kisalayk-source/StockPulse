"""Government provider normalization, mapping, scoring, and API tests."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_session, init_db, reset_db_state
from app.dependencies import Services
from app.government.clients.sam_gov import normalize_sam_opportunity
from app.government.clients.usa_spending import normalize_usa_award, normalize_usa_obligation
from app.government.mapping import GovernmentCompanyMapper
from app.government.scoring import compute_government_score, materiality_value
from app.government.service import GovernmentService
from app.government.types import NormalizedGovernmentEvent
from app.main import create_app
from app.sec.db_models import SecCompanyMapping
from test_api import FakeAlpaca, FakeFinnhub, FakeKronos, FakeSec, register_and_headers, settings


def test_normalize_sam_solicitation():
    event = normalize_sam_opportunity(
        {
            "noticeId": "abc123",
            "title": "IT Support IDIQ",
            "type": "o",
            "postedDate": "05/01/2024",
            "solicitationNumber": "SOL-1",
            "naicsCode": "541512",
            "fullParentPathName": "DEPT OF DEFENSE",
            "uiLink": "https://sam.gov/opp/abc123",
            "awardCeiling": 500_000_000,
        }
    )
    assert event.event_type == "SOLICITATION"
    assert event.source == "sam_gov"
    assert event.event_id == "sam:abc123"
    assert event.ceiling_amount == 500_000_000
    assert event.published_at is not None


def test_normalize_usa_award_and_obligation():
    row = {
        "Award ID": "HQ001",
        "generated_internal_id": "CONT_ID_1",
        "Recipient Name": "Lockheed Martin Corp",
        "Recipient UEI": "UEI123",
        "Award Amount": 420_000_000,
        "Total Outlays": 85_000_000,
        "Awarding Agency": "Department of Defense",
        "Start Date": "2024-05-15",
        "Award Type": "Definitive Contract",
        "Description": "Missile support",
    }
    award = normalize_usa_award(row)
    obligation = normalize_usa_obligation(row)
    assert award.event_type == "AWARD"
    assert award.awarded_amount == 420_000_000
    assert obligation is not None
    assert obligation.event_type == "OBLIGATION"
    assert obligation.obligated_amount == 85_000_000


def test_materiality_ignores_idiq_ceiling_only():
    event = {
        "event_type": "AWARD",
        "ceiling_amount": 500_000_000,
        "awarded_amount": None,
        "obligated_amount": None,
        "idiq": True,
    }
    assert materiality_value(event) is None


def test_scoring_award_sole_source_and_idiq_penalty():
    config = {
        "scoring": {
            "award": 30,
            "sole_source": 20,
            "idiq_ceiling_only": -20,
            "incumbent": 5,
            "new_customer": 10,
            "large_opportunity": 15,
            "multi_year": 10,
            "material_revenue": 10,
            "backlog_impact": 10,
            "option_only": -15,
            "immaterial_contract": -10,
        },
        "early_signal": {"AWARD": 50, "SOLICITATION": 70},
        "thresholds": {
            "large_opportunity_amount": 50_000_000,
            "material_revenue_ratio": 0.05,
            "immaterial_revenue_ratio": 0.005,
            "multi_year_days": 365,
        },
    }
    events = [
        {
            "event_type": "AWARD",
            "agency": "DoD",
            "sole_source": True,
            "awarded_amount": 100_000_000,
            "idiq": False,
        }
    ]
    result = compute_government_score(events, config=config, annual_revenue=2_000_000_000)
    assert result["government_score"] >= 50
    assert result["flags"]["sole_source"] is True
    assert result["flags"]["has_award"] is True

    idiq_only = [
        {
            "event_type": "SOLICITATION",
            "agency": "DoD",
            "idiq": True,
            "ceiling_amount": 1_000_000_000,
            "estimated_value": 1_000_000_000,
        }
    ]
    idiq_result = compute_government_score(idiq_only, config=config, known_agencies={"nasa"})
    assert idiq_result["flags"]["idiq_ceiling_only"] is True


def test_mapper_cik_and_unknown_company():
    reset_db_state()
    config = settings(government_enabled=True)
    init_db(config)
    session = next(get_session())
    session.add(
        SecCompanyMapping(
            ticker="LMT",
            cik="0000936468",
            company_name="Lockheed Martin Corporation",
        )
    )
    session.commit()

    mapper = GovernmentCompanyMapper(
        {"mapping": {"min_confidence": 0.75, "fuzzy_min_confidence": 0.55, "fuzzy_accept_confidence": 0.85}}
    )
    by_cik = mapper.resolve(session, cik="936468")
    assert by_cik.ticker == "LMT"
    assert by_cik.confidence >= 0.9
    assert mapper.is_confident(by_cik.confidence)

    fuzzy = mapper.resolve(session, company_name="Lockheed Martin Corp")
    assert fuzzy.ticker == "LMT"

    unknown = mapper.resolve(session, company_name="Completely Unknown Contractor XYZ")
    assert unknown.ticker is None or not mapper.is_confident(unknown.confidence)
    session.close()


def test_dedupe_events():
    reset_db_state()
    config = settings(government_enabled=True)
    init_db(config)
    session = next(get_session())
    session.add(SecCompanyMapping(ticker="LMT", cik="0000936468", company_name="Lockheed Martin Corporation"))
    session.commit()

    service = GovernmentService(config)
    event = NormalizedGovernmentEvent(
        event_type="AWARD",
        event_id="usa:award:1",
        source="usaspending",
        company_name="Lockheed Martin Corporation",
        awarded_amount=10_000_000,
        agency="DoD",
        published_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        event_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )
    _, first = service.upsert_event(session, event, force_ticker="LMT")
    _, second = service.upsert_event(session, event, force_ticker="LMT")
    session.commit()
    assert first is True
    assert second is False
    session.close()


def test_government_api_shape():
    reset_db_state()
    config = settings(
        government_enabled=True,
        prediction_enabled=False,
        agent_scheduler_enabled=False,
        sec_enabled=False,
    )
    gov = GovernmentService(config)
    services = Services(
        config,
        FakeAlpaca(),
        FakeFinnhub(),
        FakeKronos(),
        FakeSec(),
        government=gov,
    )
    with TestClient(create_app(config, services)) as client:
        headers = register_and_headers(client, with_alpaca=False)
        session = next(get_session())
        session.add(SecCompanyMapping(ticker="LMT", cik="0000936468", company_name="Lockheed Martin Corporation"))
        event = NormalizedGovernmentEvent(
            event_type="AWARD",
            event_id=f"usa:award:{uuid4().hex[:8]}",
            source="usaspending",
            company_name="Lockheed Martin Corporation",
            awarded_amount=420_000_000,
            agency="Department of Defense",
            sole_source=True,
            title="DoD award",
            published_at=datetime(2024, 5, 20, tzinfo=timezone.utc),
            event_at=datetime(2024, 5, 20, tzinfo=timezone.utc),
        )
        gov.upsert_event(session, event, force_ticker="LMT")
        session.commit()
        session.close()

        response = client.get("/api/v1/stocks/LMT/government", headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["ticker"] == "LMT"
        assert "government" in payload
        assert "score" in payload["government"]
        assert "alerts" in payload
        assert "recent_activity" in payload


class _RecordingSam:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def search_opportunities(self, **kwargs):
        self.calls.append(kwargs)
        return []


class _RecordingUsa:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def search_awards(self, **kwargs):
        self.calls.append(kwargs)
        return []


def test_sync_skips_fund_etf_tickers():
    import asyncio

    reset_db_state()
    config = settings(government_enabled=True)
    init_db(config)
    session = next(get_session())
    session.add(SecCompanyMapping(ticker="SPY", cik="0000884394", company_name="SPDR S&P 500 ETF TRUST"))
    session.commit()
    sam = _RecordingSam()
    usa = _RecordingUsa()
    service = GovernmentService(config, sam=sam, usa=usa)
    result = asyncio.run(service.sync_ticker(session, "SPY"))
    session.close()
    assert result["skipped"] == "non_contractor"
    assert result["fetched"] == 0
    assert sam.calls == []
    assert usa.calls == []


def test_analysis_payload_explains_etf_skip():
    reset_db_state()
    config = settings(government_enabled=True)
    init_db(config)
    session = next(get_session())
    session.add(SecCompanyMapping(ticker="SPY", cik="0000884394", company_name="SPDR S&P 500 ETF TRUST"))
    session.commit()
    service = GovernmentService(config)
    payload = service.analysis_payload(
        session,
        "SPY",
        sync_meta={"skipped": "non_contractor", "provider_errors": []},
    )
    session.close()
    assert any("not a government contractor" in alert["message"] for alert in payload["alerts"])


def test_sync_searches_usaspending_by_company_not_sam_title():
    import asyncio

    reset_db_state()
    config = settings(government_enabled=True)
    init_db(config)
    session = next(get_session())
    session.add(SecCompanyMapping(ticker="BA", cik="0000012927", company_name="BOEING CO"))
    session.commit()
    sam = _RecordingSam()
    usa = _RecordingUsa()
    service = GovernmentService(config, sam=sam, usa=usa)
    result = asyncio.run(service.sync_ticker(session, "BA"))
    session.close()
    assert "skipped" not in result
    assert sam.calls == []
    assert len(usa.calls) == 1
    assert usa.calls[0]["recipient_name"] == "BOEING CO"


class _CaptureUsaHttp:
    def __init__(self) -> None:
        self.body: dict | None = None

    async def post(self, url: str, json=None):
        self.body = json

        class _Resp:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {"results": []}

        return _Resp()

    async def aclose(self) -> None:
        return None


def test_usaspending_does_not_and_keyword_with_recipient():
    import asyncio

    from app.government.clients.usa_spending import UsaSpendingClient

    config = settings(government_enabled=True)
    capture = _CaptureUsaHttp()
    client = UsaSpendingClient(config, client=capture)
    asyncio.run(client.search_awards(recipient_name="BOEING CO", keyword="BOEING CO"))
    filters = (capture.body or {}).get("filters") or {}
    assert filters.get("recipient_search_text") == ["BOEING CO"]
    assert "keywords" not in filters


def test_sync_uses_sam_uei_when_mapped():
    import asyncio

    from app.government.db_models import GovernmentCompanyMapping

    reset_db_state()
    config = settings(government_enabled=True)
    init_db(config)
    session = next(get_session())
    session.add(SecCompanyMapping(ticker="BA", cik="0000012927", company_name="BOEING CO"))
    session.add(
        GovernmentCompanyMapping(
            ticker="BA",
            uei="UEIBA1",
            company_name="BOEING CO",
            confidence=1.0,
            method="manual",
        )
    )
    session.commit()
    sam = _RecordingSam()
    sam.api_key = "test-key"
    usa = _RecordingUsa()
    service = GovernmentService(config, sam=sam, usa=usa)
    asyncio.run(service.sync_ticker(session, "BA"))
    session.close()
    assert len(sam.calls) == 1
    assert sam.calls[0]["uei"] == "UEIBA1"
    assert "keyword" not in sam.calls[0] or sam.calls[0].get("keyword") in {None, ""}


def test_lmt_uses_contractor_name_hint_without_sec_mapping():
    reset_db_state()
    config = settings(government_enabled=True)
    init_db(config)
    session = next(get_session())
    service = GovernmentService(config)
    assert service._company_name_for_ticker(session, "LMT") == "LOCKHEED MARTIN"
    session.close()
