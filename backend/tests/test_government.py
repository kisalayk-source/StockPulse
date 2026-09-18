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
