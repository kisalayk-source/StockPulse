import asyncio

import httpx
import pytest

from app.config import Settings
from app.sec.client import SecClient, rank_filing_documents
from app.sec.submissions import TickerCikMapper
from app.services.providers import ProviderUnavailable


@pytest.fixture
def settings() -> Settings:
    return Settings(
        sec_enabled=True,
        sec_user_agent="StockPulse test@example.com",
        sec_requests_per_second=8,
        sec_cache_ttl_seconds=3600,
    )


def test_company_tickers_cached(settings: Settings) -> None:
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}})

    async def run() -> None:
        client = SecClient(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        first = await client.company_tickers()
        second = await client.company_tickers()
        assert first == second
        assert calls["count"] == 1
        await client.aclose()

    asyncio.run(run())


def test_mapper_resolves_ticker(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"0": {"cik_str": 34088, "ticker": "XOM", "title": "EXXON MOBIL CORP"}})

    async def run() -> None:
        client = SecClient(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        mapper = TickerCikMapper(settings, client)
        mapping = await mapper.resolve_cik("XOM")
        assert mapping is not None
        assert mapping["cik"] == "0000034088"
        await client.aclose()

    asyncio.run(run())


def test_sec_disabled_raises(settings: Settings) -> None:
    settings.sec_enabled = False
    client = SecClient(settings)

    async def run() -> None:
        with pytest.raises(ProviderUnavailable):
            await client.company_tickers()
        await client.aclose()

    asyncio.run(run())


def test_fetch_filing_documents_selects_primary_and_infotable(settings: Settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/index.json"):
            return httpx.Response(
                200,
                json={
                    "directory": {
                        "item": [
                            {"name": "primary_doc.xml"},
                            {"name": "infotable.xml"},
                        ]
                    }
                },
            )
        if "primary_doc.xml" in request.url.path:
            return httpx.Response(200, text="<primary><name>Fund A</name></primary>")
        if "infotable.xml" in request.url.path:
            return httpx.Response(200, text="<informationTable><infoTable/></informationTable>")
        return httpx.Response(404)

    async def run() -> None:
        client = SecClient(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        docs = await client.fetch_filing_documents("0000034088", "0001-001", "13F-HR")
        assert "primary" in docs
        assert "infotable" in docs
        await client.aclose()

    asyncio.run(run())


def test_rank_filing_documents_prefers_form4_xml() -> None:
    ranked = rank_filing_documents(
        ["report.htm", "primary_doc.xml", "ownership.xml", "other.xml"],
        "4",
        "4",
    )
    assert ranked[0] == "ownership.xml"
