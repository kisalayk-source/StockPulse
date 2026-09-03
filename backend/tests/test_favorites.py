"""Favorites API tests."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import reset_db_state
from app.dependencies import Services
from app.main import create_app


class FakeSec:
    def scan_status(self):
        return {"status": "idle", "scanned": 0, "total": 0, "errors": []}

    def start_accumulation_scan(self, services, *, refresh=False):
        return {"status": "ready", "scanned": 0, "total": 0, "errors": []}

    def maybe_auto_scan(self, session, services):
        return None


class FakeFinnhub:
    async def search(self, query: str) -> list[dict]:
        return []

    async def company_profile(self, symbol: str) -> dict:
        return {}

    async def extended_fundamentals(self, symbol: str) -> dict:
        return {}

    async def company_news(self, symbol: str, limit: int) -> list[dict]:
        return []

    async def fundamentals(self, symbol: str) -> dict:
        return {}

    async def news_sentiment(self, symbol: str) -> dict:
        return {"label": "neutral"}


class FakeKronos:
    def forecast(self, *args, **kwargs) -> dict:
        return {"symbol": "AAPL", "forecast": [], "trend": {"direction": "flat", "forecast_change": 0}}

    def scan_movers(self, limit: int = 50, refresh: bool = False) -> dict:
        return {"movers": [], "scanned": 0}


class FakeAlpaca:
    def search_assets(self, query: str, mode: str) -> list[dict]:
        return []

    def snapshot(self, symbol: str) -> dict:
        return {"symbol": symbol.upper(), "current_price": 100.0}

    def bars(self, symbol: str, timeframe: str, start, end, limit: int) -> list[dict]:
        return []

    def account(self, mode: str) -> dict:
        return {"id": "account", "mode": mode}

    def market_clock(self, mode: str = "paper") -> dict:
        return {"is_open": True, "session": "regular"}


def settings(**overrides) -> Settings:
    defaults = {"database_url": "sqlite://"}
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def make_client() -> TestClient:
    reset_db_state()
    config = settings()
    services = Services(config, FakeAlpaca(), FakeFinnhub(), FakeKronos(), FakeSec())
    return TestClient(create_app(config, services))


def register_headers(client: TestClient) -> dict[str, str]:
    email = f"fav-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_favorites_add_list_remove() -> None:
    with make_client() as client:
        headers = register_headers(client)
        empty = client.get("/api/v1/favorites", headers=headers)
        assert empty.status_code == 200
        assert empty.json()["favorites"] == []

        added = client.put("/api/v1/favorites/AAPL", headers=headers)
        assert added.status_code == 200
        assert added.json()["ticker"] == "AAPL"

        listed = client.get("/api/v1/favorites", headers=headers)
        assert listed.status_code == 200
        tickers = [item["ticker"] for item in listed.json()["favorites"]]
        assert tickers == ["AAPL"]

        again = client.put("/api/v1/favorites/aapl", headers=headers)
        assert again.status_code == 200
        assert len(client.get("/api/v1/favorites", headers=headers).json()["favorites"]) == 1

        removed = client.delete("/api/v1/favorites/AAPL", headers=headers)
        assert removed.status_code == 204
        assert client.get("/api/v1/favorites", headers=headers).json()["favorites"] == []


def test_favorites_invalid_ticker() -> None:
    with make_client() as client:
        headers = register_headers(client)
        bad = client.put("/api/v1/favorites/BADTICKER!!!", headers=headers)
        assert bad.status_code == 422
