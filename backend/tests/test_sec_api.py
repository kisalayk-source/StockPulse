from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_session, reset_db_state
from app.dependencies import Services, build_services
from app.main import create_app


class FakeFinnhubExtended:
    async def company_profile(self, symbol: str):
        return {"sector": "Energy", "industry": "Oil", "exchange": "NYSE"}

    async def extended_fundamentals(self, symbol: str):
        return {"pe_ratio": 12.0, "revenue_growth": 0.08, "eps_growth": 0.05, "roic": 0.12}


class FakeAlpacaBars:
    def bars(self, symbol: str, timeframe: str, start, end, limit: int):
        return [
            {
                "timestamp": f"2024-01-{idx + 1:02d}T00:00:00+00:00",
                "open": 100 + idx * 0.1,
                "high": 101 + idx * 0.1,
                "low": 99 + idx * 0.1,
                "close": 100 + idx * 0.2,
                "volume": 1000000 + idx * 1000,
            }
            for idx in range(60)
        ]


@pytest.fixture
def seeded_client():
    settings = Settings(
        database_url="sqlite:///:memory:",
        sec_enabled=False,
        jwt_secret="test-secret-key-32-characters-min",
    )
    services = Services(
        settings=settings,
        alpaca=FakeAlpacaBars(),
        finnhub=FakeFinnhubExtended(),
        kronos=object(),
        sec=build_services(settings).sec,
    )
    app = create_app(settings=settings, services=services)
    with TestClient(app) as client:
        email = f"sec-{uuid4().hex}@example.com"
        register = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
        token = register.json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
        gen = get_session()
        session = next(gen)
        xml_text = (Path(__file__).parent / "fixtures" / "sec" / "form_13f_infotable.xml").read_text(encoding="utf-8")
        services.sec.ingest_fixture_filing(
            session,
            "XOM",
            {
                "accession_number": "0001-001",
                "form_type": "13F-HR",
                "form_family": "13F",
                "filing_date": date(2024, 3, 1),
                "report_period": date(2023, 12, 31),
                "cik": "0000034088",
                "sector": "Energy",
            },
            xml_text,
        )
        try:
            next(gen)
        except StopIteration:
            pass
        yield client
    reset_db_state()


def test_accumulation_endpoint(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/v1/stocks/XOM/accumulation")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "XOM"
    assert 0 <= payload["score"] <= 100
    assert "components" in payload


def test_top_accumulation_endpoint(seeded_client: TestClient) -> None:
    seeded_client.get("/api/v1/stocks/XOM/accumulation")
    response = seeded_client.get("/api/v1/accumulation/top")
    assert response.status_code == 200
    assert "results" in response.json()


def test_research_query_endpoint(seeded_client: TestClient) -> None:
    seeded_client.get("/api/v1/stocks/XOM/accumulation")
    response = seeded_client.post(
        "/api/v1/research/query",
        json={"query": "Which energy stocks have strong institutional accumulation?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "narrative" in payload
    assert payload["filters"].get("sector") == "Energy"


def test_list_sectors_endpoint(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/v1/sectors")
    assert response.status_code == 200
    assert "sectors" in response.json()


def test_scan_status_endpoint(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/v1/accumulation/scan/status")
    assert response.status_code == 200
    assert "status" in response.json()


def test_filings_endpoint(seeded_client: TestClient) -> None:
    from app.db import get_session

    services = seeded_client.app.state.services
    gen = get_session()
    session = next(gen)
    xml_text = (Path(__file__).parent / "fixtures" / "sec" / "form_4.xml").read_text(encoding="utf-8")
    services.sec.ingest_fixture_filing(
        session,
        "XOM",
        {
            "accession_number": "0001-002",
            "form_type": "4",
            "form_family": "4",
            "filing_date": date.today(),
            "cik": "0000034088",
            "sector": "Energy",
        },
        xml_text,
    )
    try:
        next(gen)
    except StopIteration:
        pass
    response = seeded_client.get("/api/v1/stocks/XOM/filings?months=6")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "XOM"
    assert payload["summary"]["4"] >= 1
    form4_filings = [row for row in payload["filings"] if row["form_family"] == "4"]
    assert form4_filings
    assert form4_filings[0]["filer_name"]
    assert form4_filings[0]["action"]
    assert form4_filings[0]["action_tone"] in {"positive", "negative", "neutral"}
    assert isinstance(form4_filings[0].get("details"), list)
    assert form4_filings[0]["details"]
    assert form4_filings[0]["details"][0]["type"] == "insider"
    assert form4_filings[0]["details"][0]["entity"]


def test_filings_analysis_endpoint(seeded_client: TestClient) -> None:
    from app.db import get_session

    services = seeded_client.app.state.services
    gen = get_session()
    session = next(gen)
    xml_text = (Path(__file__).parent / "fixtures" / "sec" / "form_4.xml").read_text(encoding="utf-8")
    services.sec.ingest_fixture_filing(
        session,
        "XOM",
        {
            "accession_number": "0001-003",
            "form_type": "4",
            "form_family": "4",
            "filing_date": date.today(),
            "cik": "0000034088",
            "sector": "Energy",
        },
        xml_text,
    )
    try:
        next(gen)
    except StopIteration:
        pass
    response = seeded_client.get("/api/v1/stocks/XOM/filings/analysis?months=6")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "XOM"
    assert payload["sentiment"] in {"good", "bad", "mixed", "neutral"}
    assert payload["sentiment_label"]
    assert isinstance(payload["gist"], list)
    assert payload["headline"]
    assert payload["source"] in {"llm", "rules"}
    assert payload["disclaimer"]


def test_filings_analysis_rule_based_sentiment(seeded_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.db import get_session
    from app.services import filings_analysis

    async def fake_llm(*_args, **_kwargs):
        return None

    monkeypatch.setattr(filings_analysis, "_llm_analysis", fake_llm)

    services = seeded_client.app.state.services
    gen = get_session()
    session = next(gen)
    xml_text = (Path(__file__).parent / "fixtures" / "sec" / "form_4.xml").read_text(encoding="utf-8")
    services.sec.ingest_fixture_filing(
        session,
        "XOM",
        {
            "accession_number": "0001-004",
            "form_type": "4",
            "form_family": "4",
            "filing_date": date.today(),
            "cik": "0000034088",
            "sector": "Energy",
        },
        xml_text,
    )
    try:
        next(gen)
    except StopIteration:
        pass
    response = seeded_client.get("/api/v1/stocks/XOM/filings/analysis?months=6")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "rules"
    assert payload["sentiment"] in {"good", "mixed", "neutral"}


def test_filings_backfill_parses_existing_shell(seeded_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.db import get_session
    from app.sec.db_models import SecCompanyMapping, SecFiling

    services = seeded_client.app.state.services
    gen = get_session()
    session = next(gen)
    xml_text = (Path(__file__).parent / "fixtures" / "sec" / "form_4.xml").read_text(encoding="utf-8")
    accession = "0001-shell"
    session.add(
        SecFiling(
            accession_number=accession,
            cik="0000034088",
            ticker="XOM",
            form_type="4",
            form_family="4",
            filing_date=date.today(),
        )
    )
    mapping = session.query(SecCompanyMapping).filter(SecCompanyMapping.ticker == "XOM").one_or_none()
    if mapping is None:
        session.add(SecCompanyMapping(ticker="XOM", cik="0000034088", company_name="Exxon"))
    session.flush()

    async def fake_ranked_docs(*_args, **_kwargs):
        return [("form4.xml", xml_text)]

    monkeypatch.setattr(services.sec.client, "fetch_ranked_filing_documents", fake_ranked_docs)
    try:
        next(gen)
    except StopIteration:
        pass

    response = seeded_client.get("/api/v1/stocks/XOM/filings?months=6")
    assert response.status_code == 200
    filing = next(row for row in response.json()["filings"] if row["accession_number"] == accession)
    assert filing["filer_name"] == "Jane Smith"
    assert filing["action"]
    assert filing["details"]
