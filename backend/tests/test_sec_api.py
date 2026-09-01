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
