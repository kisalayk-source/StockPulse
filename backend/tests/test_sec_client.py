import asyncio

import httpx
import pytest

from app.config import Settings
from app.sec.client import SecClient
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
