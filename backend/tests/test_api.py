from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import reset_db_state
from app.dependencies import Services
from app.main import create_app
from app.schemas import EquityOrderRequest, OptionOrderRequest, OrderPreviewRequest
from app.services.providers import (
    AlpacaService,
    FinnhubService,
    ProviderUnavailable,
    classify_article_sentiment,
    normalize_news,
    rank_search_results,
)
from app.sec.service import SecService


class FakeSec:
    async def accumulation_for_ticker(self, session, ticker, alpaca, finnhub, sync=True):
        return {
            "ticker": ticker.upper(),
            "score": 50.0,
            "signal": "NEUTRAL",
            "classification": "NEUTRAL",
            "components": {},
            "events": [],
            "history": [],
            "as_of": "2024-01-01T00:00:00+00:00",
            "provider_errors": [],
        }

    def sec_intelligence(self, session, ticker, accumulation):
        return {
            "ticker": ticker.upper(),
            "accumulation": accumulation,
            "institutional_changes": [],
            "insider_transactions": [],
            "major_holder_changes": [],
            "caveats": [],
        }

    async def sync_ticker(self, *args, **kwargs):
        return None

    def institutional_payload(self, session, ticker):
        return {"ticker": ticker.upper(), "changes": []}

    def insiders_payload(self, session, ticker):
        return {"ticker": ticker.upper(), "transactions": []}

    def top_accumulation(self, session, **kwargs):
        return []

    def sector_accumulation(self, session, sector):
        return {
            "sector": sector,
            "ticker_count": 0,
            "avg_score": 50.0,
            "pct_increasing": 0.0,
            "pct_decreasing": 0.0,
            "stocks": [],
        }

    def list_sectors(self, session):
        return [{"sector": "Technology", "ticker_count": 0}]

    def scan_status(self):
        return {"status": "idle", "scanned": 0, "total": 0, "errors": []}

    def start_accumulation_scan(self, services, *, refresh=False):
        return {"status": "ready", "scanned": 0, "total": 0, "errors": []}

    def maybe_auto_scan(self, session, services):
        return None

    async def mini_scan(self, services, tickers, *, cap=25):
        return None

    async def recent_filings_payload(self, session, ticker, finnhub, *, months=6, limit=100):
        return {
            "ticker": ticker.upper(),
            "months": months,
            "cutoff_date": "2024-01-01",
            "summary": {"13F": 0, "13D": 0, "13G": 0, "4": 0},
            "filings": [],
            "insider_transactions": [],
            "beneficial_ownership": [],
            "provider_errors": [],
        }


class FakeAlpaca:
    def __init__(self) -> None:
        self.submitted: list[object] = []
        self.canceled: list[tuple[str, str]] = []
        self.replaced: list[tuple[str, object]] = []

    def search_assets(self, query: str, mode: str) -> list[dict]:
        return [{"symbol": "AAPL", "name": "Apple Inc.", "tradable": True}]

    def snapshot(self, symbol: str) -> dict:
        return {
            "symbol": symbol.upper(),
            "current_price": 200.0,
            "timestamp": "2026-08-12T18:00:00+00:00",
            "session": "regular",
            "daily": {"open": 198.0, "high": 201.0, "low": 197.0, "close": 200.0},
            "previous_daily": None,
        }

    def news(self, symbol: str, limit: int) -> list[dict]:
        return [
            {
                "id": f"{symbol}-news",
                "headline": f"{symbol} update",
                "source": "Benzinga",
                "url": "https://example.com/news",
                "created_at": "2026-08-12T17:00:00+00:00",
                "symbols": [symbol.upper()],
            }
        ]

    def bars(self, symbol: str, timeframe: str, start, end, limit: int) -> list[dict]:
        return [
            {
                "timestamp": "2026-08-12T18:00:00+00:00",
                "open": 198.0,
                "high": 201.0,
                "low": 197.0,
                "close": 200.0,
                "volume": 1000,
            }
        ]

    def account(self, mode: str) -> dict:
        return {"id": "account", "mode": mode}

    def realized_pl(self, mode: str) -> dict:
        return {"realized_pl": 42.5, "fill_count": 3, "as_of": "2026-08-25T12:00:00+00:00"}

    def positions(self, mode: str) -> list[dict]:
        return [{"symbol": "AAPL", "qty": "1"}]

    def orders(self, mode: str, status: str, limit: int) -> list[dict]:
        return []

    def option_contracts(
        self, underlying: str, expiration, contract_type, limit: int, mode: str
    ) -> list[dict]:
        return [{"symbol": "AAPL260821C00200000", "tradable": True}]

    def option_chain(self, underlying: str, expiration=None, contract_type=None) -> dict:
        return {"AAPL260821C00200000": {"latest_quote": {"ask_price": 5.0}}}

    def submit_equity_order(self, order) -> dict:
        self.submitted.append(order)
        return {"id": "equity-order", "status": "accepted"}

    def submit_option_order(self, order) -> dict:
        self.submitted.append(order)
        return {"id": "option-order", "status": "accepted"}

    def preview_order(self, order) -> dict:
        return {"ok": True, "estimated_cost": 200.0, "warnings": [], "risk": {"new_buys_halted": False}}

    def cancel_order(self, order_id: str, mode: str) -> dict:
        self.canceled.append((order_id, mode))
        return {"id": order_id, "status": "cancel_requested"}

    def replace_order(self, order_id: str, replacement) -> dict:
        self.replaced.append((order_id, replacement))
        return {"id": order_id, "status": "replaced", "limit_price": replacement.limit_price}

    def market_clock(self, mode: str = "paper") -> dict:
        return {
            "is_open": True,
            "session": "regular",
            "timestamp": "2026-08-12T14:30:00+00:00",
            "next_open": "2026-08-13T13:30:00+00:00",
            "next_close": "2026-08-12T20:00:00+00:00",
        }


class FakeFinnhub:
    async def search(self, query: str) -> list[dict]:
        return [{"symbol": "AAPL", "name": "Apple Inc.", "type": "Common Stock"}]

    async def company_profile(self, symbol: str) -> dict:
        return {"sector": "Technology", "industry": "Technology", "exchange": "NASDAQ"}

    async def extended_fundamentals(self, symbol: str) -> dict:
        return {"pe_ratio": 20.0, "revenue_growth": 0.1, "eps_growth": 0.05, "roic": 0.15}

    async def company_news(self, symbol: str, limit: int) -> list[dict]:
        return [
            {
                "id": f"{symbol}-fh",
                "headline": f"{symbol} company news",
                "source": "Reuters",
                "url": "https://example.com/company-news",
                "created_at": "2026-08-12T16:00:00+00:00",
                "symbols": [symbol.upper()],
            }
        ]

    async def fundamentals(self, symbol: str) -> dict:
        return {
            "pe_ratio": 31.2,
            "market_cap": 3_100_000,
            "dividend_yield": None,
            "eps": 6.4,
        }

    async def news_sentiment(self, symbol: str) -> dict:
        return {
            "label": "bullish",
            "bullish_percent": 0.72,
            "bearish_percent": 0.18,
            "score": 0.64,
        }


class UnavailableFinnhub:
    async def search(self, query: str) -> list[dict]:
        raise ProviderUnavailable("finnhub", "not configured")

    async def company_news(self, symbol: str, limit: int) -> list[dict]:
        raise ProviderUnavailable("finnhub", "not configured")

    async def fundamentals(self, symbol: str) -> dict:
        raise ProviderUnavailable("finnhub", "not configured")

    async def news_sentiment(self, symbol: str) -> dict:
        raise ProviderUnavailable("finnhub", "not configured")


class FakeKronos:
    loaded = False

    def forecast(self, symbol, preset, timeframe, context, horizon, bars=None, use_cache=True, evaluate=True, engine="kronos") -> dict:
        return {
            "symbol": symbol.upper(),
            "preset": preset,
            "historical": [],
            "forecast": [],
            "trend": {"direction": "flat", "forecast_change": 0},
            "model": {"id": "ensemble" if engine == "ensemble" else "NeoQuasar/Kronos-small", "engine": engine},
        }

    def scan_movers(self, limit: int = 50, refresh: bool = False) -> dict:
        names = ["NVDA", "TSLA", "AAPL", "AMD", "META"]
        movers = [
            {
                "symbol": symbol,
                "last_price": 100 + index,
                "predicted_price": 110 + index,
                "forecast_change": 0.12 - index * 0.02,
                "direction": "up" if index < 3 else "down",
                "day_change": 0.03 - index * 0.01,
                "volume": 1_000_000 * (5 - index),
                "as_of": "2026-08-12T18:00:00+00:00",
            }
            for index, symbol in enumerate(names[:limit])
        ]
        return {
            "as_of": "2026-08-12T18:05:00+00:00",
            "session": "regular",
            "market_open": True,
            "preset": "scan_intraday",
            "timeframe": "5Min",
            "scanned": len(movers),
            "cached": not refresh,
            "movers": movers,
            "skipped": [],
        }


def settings(**overrides) -> Settings:
    defaults = {"database_url": "sqlite://"}
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def make_client(config: Settings | None = None, alpaca=None, finnhub=None) -> TestClient:
    reset_db_state()
    config = config or settings()
    alpaca = alpaca or FakeAlpaca()
    services = Services(config, alpaca, finnhub or FakeFinnhub(), FakeKronos(), FakeSec())
    return TestClient(create_app(config, services))


def register_and_headers(
    client: TestClient,
    *,
    email: str | None = None,
    password: str = "password123",
    with_alpaca: bool = True,
    mode: str = "paper",
) -> dict[str, str]:
    address = email or f"user-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": address, "password": password},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    if with_alpaca:
        saved = client.put(
            "/api/v1/auth/alpaca",
            headers=headers,
            json={"mode": mode, "key_id": "PKTESTKEY123456", "secret": "secretsecret12"},
        )
        assert saved.status_code == 200, saved.text
    return headers


def test_health_and_safe_config_status() -> None:
    with make_client(settings(alpaca_paper_key="key", alpaca_paper_secret="secret")) as client:
        assert client.get("/api/v1/health").json() == {"status": "ok"}
        headers = register_and_headers(client)
        response = client.get("/api/v1/config/status", headers=headers)
        assert response.status_code == 200
        assert response.json()["alpaca"]["paper_configured"] is True
        assert "reddit_configured" not in response.json()
        assert "secretsecret12" not in response.text
        assert "PKTESTKEY123456" not in response.text


def test_missing_alpaca_credentials_returns_400() -> None:
    with make_client() as client:
        headers = register_and_headers(client, with_alpaca=False)
        response = client.get("/api/v1/account", params={"mode": "paper"}, headers=headers)
    assert response.status_code == 400
    assert "Configure Alpaca paper credentials" in response.json()["detail"]


def test_register_login_and_me() -> None:
    with make_client() as client:
        created = client.post(
            "/api/v1/auth/register",
            json={"email": "trader@example.com", "password": "password123"},
        )
        assert created.status_code == 201
        token = created.json()["access_token"]
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "trader@example.com"
        assert me.json()["alpaca"]["paper"]["configured"] is False
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "trader@example.com", "password": "password123"},
        )
        assert login.status_code == 200
        assert login.json()["access_token"]


def test_unauthenticated_trading_is_rejected() -> None:
    with make_client() as client:
        response = client.get("/api/v1/account", params={"mode": "paper"})
    assert response.status_code == 401


def test_finnhub_fundamental_normalization_and_nulls() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["token"] == "test-key"
        return httpx.Response(
            200,
            json={
                "metric": {
                    "peBasicExclExtraTTM": "24.5",
                    "marketCapitalization": 12345,
                    "dividendYieldIndicatedAnnual": 0.5,
                    "epsBasicExclExtraItemsTTM": "not-a-number",
                }
            },
        )

    async def run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = FinnhubService(settings(finnhub_api_key="test-key"), client)
        result = await service.fundamentals("AAPL")
        await client.aclose()
        assert result == {
            "pe_ratio": 24.5,
            "market_cap": 12_345_000_000.0,
            "dividend_yield": 0.005,
            "eps": None,
        }

    import asyncio

    asyncio.run(run())


def test_finnhub_news_sentiment_classifies_bullish_bearish_and_neutral() -> None:
    payloads = [
        (
            {"sentiment": {"bullishPercent": 0.72, "bearishPercent": 0.18}, "companyNewsScore": 0.8},
            "bullish",
        ),
        (
            {"sentiment": {"bullishPercent": 0.2, "bearishPercent": 0.7}, "companyNewsScore": 0.3},
            "bearish",
        ),
        (
            {"sentiment": {"bullishPercent": 0.48, "bearishPercent": 0.52}, "companyNewsScore": 0.5},
            "neutral",
        ),
    ]

    async def run() -> None:
        for payload, expected in payloads:
            async def handler(request: httpx.Request, body=payload) -> httpx.Response:
                assert "/news-sentiment" in str(request.url)
                return httpx.Response(200, json=body)

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            service = FinnhubService(settings(finnhub_api_key="test-key"), client)
            result = await service.news_sentiment("AAPL")
            await client.aclose()
            assert result["label"] == expected

    import asyncio

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "paper", "symbol": "AAPL", "side": "buy", "qty": 0},
        {
            "mode": "paper",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1,
            "notional": 100,
        },
        {"mode": "paper", "symbol": "AAPL", "side": "buy", "qty": 1, "type": "limit"},
    ],
)
def test_equity_order_input_validation(payload: dict) -> None:
    with make_client() as client:
        headers = register_and_headers(client)
        response = client.post("/api/v1/orders/equity", json=payload, headers=headers)
    assert response.status_code == 422


def test_live_order_is_blocked_before_provider_call() -> None:
    fake = FakeAlpaca()
    with make_client(
        settings(
            allow_live_trading=False,
            live_confirmation_token="CONFIRM-LIVE",
            alpaca_live_key="key",
            alpaca_live_secret="secret",
        ),
        alpaca=fake,
    ) as client:
        headers = register_and_headers(client)
        response = client.post(
            "/api/v1/orders/equity",
            headers=headers,
            json={
                "mode": "live",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1,
                "live_confirmation_token": "CONFIRM-LIVE",
            },
        )
    assert response.status_code == 403
    assert fake.submitted == []


def test_live_order_requires_exact_token_when_enabled() -> None:
    fake = FakeAlpaca()
    config = settings(allow_live_trading=True, live_confirmation_token="EXACT")
    with make_client(config, alpaca=fake) as client:
        headers = register_and_headers(client, with_alpaca=False)
        saved = client.put(
            "/api/v1/auth/alpaca",
            headers=headers,
            json={"mode": "live", "key_id": "PKTESTKEY123456", "secret": "secretsecret12"},
        )
        assert saved.status_code == 200, saved.text
        wrong = client.post(
            "/api/v1/orders/equity",
            headers=headers,
            json={
                "mode": "live",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1,
                "live_confirmation_token": "wrong",
            },
        )
        valid = client.post(
            "/api/v1/orders/equity",
            headers=headers,
            json={
                "mode": "live",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1,
                "live_confirmation_token": "EXACT",
            },
        )
    assert wrong.status_code == 403
    assert valid.status_code == 201
    assert len(fake.submitted) == 1


def test_open_order_can_be_canceled_or_replaced() -> None:
    fake = FakeAlpaca()
    with make_client(alpaca=fake) as client:
        headers = register_and_headers(client)
        canceled = client.request(
            "DELETE",
            "/api/v1/orders/order-1",
            headers=headers,
            json={"mode": "paper"},
        )
        replaced = client.patch(
            "/api/v1/orders/order-2",
            headers=headers,
            json={"mode": "paper", "limit_price": 199.5},
        )

    assert canceled.status_code == 200
    assert canceled.json()["status"] == "cancel_requested"
    assert fake.canceled == [("order-1", "paper")]
    assert replaced.status_code == 200
    assert fake.replaced[0][0] == "order-2"
    assert fake.replaced[0][1].limit_price == 199.5


def test_search_ranks_common_tickers_ahead_of_substring_noise() -> None:
    buried = [
        {"symbol": f"M{index:02d}", "name": f"Metal Co {index}", "tradable": True}
        for index in range(25)
    ]
    ranked = rank_search_results(
        "meta",
        [*buried, {"symbol": "META", "name": "Meta Platforms, Inc.", "tradable": True}],
    )
    assert ranked[0]["symbol"] == "META"

    google = rank_search_results(
        "google",
        [
            {"symbol": "GOOGL", "name": "Alphabet Inc Class A", "tradable": True},
            {"symbol": "ZZZ", "name": "Google-adjacent fund", "tradable": True},
        ],
    )
    assert google[0]["symbol"] == "GOOGL"


def test_search_api_returns_ranked_common_symbols() -> None:
    class NoisyAlpaca(FakeAlpaca):
        def search_assets(self, query: str, mode: str) -> list[dict]:
            return [
                {"symbol": f"M{index:02d}", "name": f"Metal Co {index}", "tradable": True}
                for index in range(20)
            ] + [{"symbol": "META", "name": "Meta Platforms, Inc.", "tradable": True}]

    class MetaFinnhub(FakeFinnhub):
        async def search(self, query: str) -> list[dict]:
            return [{"symbol": "META", "name": "Meta Platforms Inc", "type": "Common Stock"}]

    with make_client(alpaca=NoisyAlpaca(), finnhub=MetaFinnhub()) as client:
        headers = register_and_headers(client, with_alpaca=False)
        results = client.get(
            "/api/v1/symbols/search", params={"q": "meta"}, headers=headers
        ).json()["results"]
        assert results[0]["symbol"] == "META"


def test_overview_returns_news_for_the_requested_symbol() -> None:
    with make_client() as client:
        headers = register_and_headers(client, with_alpaca=False)
        payload = client.get("/api/v1/stocks/META/overview", headers=headers).json()
    headlines = [item["headline"] for item in payload["news"]]
    assert headlines[0] == "META company news"
    assert "META update" in headlines
    assert all(item["sentiment"] in {"positive", "negative", "neutral"} for item in payload["news"])
    assert all("META" in item["headline"] or "META" in item.get("symbols", []) for item in payload["news"])


def test_normalize_news_unwraps_alpaca_news_set_and_filters_symbol() -> None:
    payload = {
        "news": [
            {"headline": "Broad market", "symbols": ["SPY"], "url": "https://example.com/spy"},
            {
                "headline": "Alphabet earnings",
                "symbols": ["GOOGL", "GOOG"],
                "url": "https://example.com/googl",
                "source": "Reuters",
                "created_at": "2026-08-12T12:00:00Z",
            },
        ],
        "next_page_token": "abc",
    }
    articles = normalize_news(payload, "GOOGL", 8)
    assert len(articles) == 1
    assert articles[0]["headline"] == "Alphabet earnings"
    assert articles[0]["sentiment"] == "neutral"


def test_article_sentiment_classifies_positive_and_negative_headlines() -> None:
    assert classify_article_sentiment("Apple earnings beat estimates") == "positive"
    assert classify_article_sentiment("Tesla faces lawsuit after sales drop") == "negative"
    assert classify_article_sentiment("Company schedules investor day") == "neutral"


def test_market_data_account_options_and_forecast_api() -> None:
    with make_client() as client:
        headers = register_and_headers(client)
        assert client.get(
            "/api/v1/symbols/search", params={"q": "apple"}, headers=headers
        ).status_code == 200
        overview = client.get("/api/v1/stocks/AAPL/overview", headers=headers)
        assert overview.status_code == 200
        assert overview.json()["fundamentals"]["dividend_yield"] is None
        assert overview.json()["public_sentiment"]["label"] == "bullish"
        assert client.get("/api/v1/stocks/AAPL/bars", headers=headers).json()["bars"]
        assert client.get(
            "/api/v1/account", params={"mode": "paper"}, headers=headers
        ).status_code == 200
        realized = client.get(
            "/api/v1/account/realized-pl", params={"mode": "paper"}, headers=headers
        )
        assert realized.status_code == 200
        assert realized.json()["realized_pl"] == 42.5
        clock = client.get("/api/v1/market/clock", headers=headers).json()
        assert clock["is_open"] is True
        assert clock["session"] == "regular"
        assert client.get(
            "/api/v1/options/contracts",
            params={"underlying": "AAPL", "mode": "paper"},
            headers=headers,
        ).status_code == 200
        assert client.get(
            "/api/v1/options/chain", params={"underlying": "AAPL"}, headers=headers
        ).status_code == 200
        forecast = client.post(
            "/api/v1/forecast", json={"symbol": "AAPL", "preset": "short"}, headers=headers
        )
        assert forecast.status_code == 200
        assert forecast.json()["symbol"] == "AAPL"
        assert forecast.json()["model"]["engine"] == "kronos"
        ensemble = client.post(
            "/api/v1/forecast",
            headers=headers,
            json={"symbol": "AAPL", "preset": "short", "engine": "ensemble"},
        )
        assert ensemble.status_code == 200
        assert ensemble.json()["model"]["engine"] == "ensemble"
        preview = client.post(
            "/api/v1/orders/preview",
            headers=headers,
            json={"kind": "equity", "mode": "paper", "symbol": "AAPL", "side": "buy", "qty": 1},
        )
        assert preview.status_code == 200
        assert preview.json()["ok"] is True
        movers = client.post(
            "/api/v1/forecast/movers", json={"refresh": True, "limit": 3}, headers=headers
        )
        assert movers.status_code == 200
        payload = movers.json()
        assert payload["cached"] is False
        assert [item["symbol"] for item in payload["movers"]] == ["NVDA", "TSLA", "AAPL"]


def test_overview_degrades_when_optional_fundamentals_are_unavailable() -> None:
    with make_client(finnhub=UnavailableFinnhub()) as client:
        headers = register_and_headers(client, with_alpaca=False)
        response = client.get("/api/v1/stocks/AAPL/overview", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["current_price"] == 200.0
    assert payload["fundamentals"] == {
        "pe_ratio": None,
        "market_cap": None,
        "dividend_yield": None,
        "eps": None,
    }
    assert payload["public_sentiment"] is None
    assert {error["provider"] for error in payload["provider_errors"]} >= {
        "finnhub",
        "finnhub_news",
        "finnhub_sentiment",
    }
    assert payload["news"][0]["headline"] == "AAPL update"


def test_option_order_validation_and_submission() -> None:
    with make_client() as client:
        headers = register_and_headers(client)
        invalid = client.post(
            "/api/v1/orders/option",
            headers=headers,
            json={
                "mode": "paper",
                "contract_symbol": "AAPL260821C00200000",
                "side": "buy",
                "qty": 1,
                "type": "limit",
            },
        )
        valid = client.post(
            "/api/v1/orders/option",
            headers=headers,
            json={
                "mode": "paper",
                "contract_symbol": "AAPL260821C00200000",
                "side": "buy",
                "qty": 1,
            },
        )
    assert invalid.status_code == 422
    assert valid.status_code == 201


def test_option_provider_uses_contract_api_and_safe_position_intent() -> None:
    class TradingClient:
        submitted = None

        def get_option_contract(self, symbol: str):
            assert symbol == "AAPL260821C00200000"
            return SimpleNamespace(tradable=True, underlying_symbol="AAPL")

        def get_account(self):
            return SimpleNamespace(equity="100000", last_equity="100000", buying_power="50000")

        def get_all_positions(self):
            return [{"symbol": "AAPL260821C00200000", "qty": "1", "market_value": "500"}]

        def submit_order(self, request):
            self.submitted = request
            return SimpleNamespace(id="option-order", status="accepted")

    client = TradingClient()
    service = AlpacaService(settings())
    service._trading = lambda mode: client
    service.option_snapshot = lambda contract, underlying: {
        "symbol": underlying,
        "contract_symbol": contract,
    }
    service.submit_option_order(
        OptionOrderRequest(
            mode="paper",
            contract_symbol="AAPL260821C00200000",
            side="sell",
            qty=1,
        )
    )

    assert client.submitted.position_intent.value == "sell_to_close"


def test_option_preview_uses_contract_premium_instead_of_underlying_price() -> None:
    class TradingClient:
        def get_option_contract(self, symbol: str):
            return SimpleNamespace(tradable=True, underlying_symbol="SPY")

        def get_account(self):
            return SimpleNamespace(equity="100000", last_equity="100000", buying_power="50000")

        def get_all_positions(self):
            return []

    service = AlpacaService(settings())
    service._trading = lambda mode: TradingClient()
    service.option_snapshot = lambda contract, underlying: {
        "symbol": underlying,
        "contract_symbol": contract,
        "bid": 0.0199,
        "ask": 0.02,
        "current_price": 0.02,
    }

    preview = service.preview_order(
        OrderPreviewRequest(
            kind="option",
            mode="paper",
            symbol="SPY",
            contract_symbol="SPY260814P00500000",
            side="buy",
            qty=1,
            position_intent="buy_to_open",
        )
    )

    assert preview["estimated_cost"] == pytest.approx(2.0)


def test_equity_provider_rejects_order_above_buying_power() -> None:
    class TradingClient:
        def get_asset(self, symbol: str):
            return SimpleNamespace(tradable=True)

        def get_account(self):
            return SimpleNamespace(buying_power="500", equity="10000", last_equity="10000")

        def get_all_positions(self):
            return []

        def submit_order(self, request):
            raise AssertionError("Order must not be submitted")

    service = AlpacaService(settings())
    service._trading = lambda mode: TradingClient()

    with pytest.raises(ValueError, match="exceeds buying power"):
        service.submit_equity_order(
            EquityOrderRequest(
                mode="paper",
                symbol="AAPL",
                side="buy",
                notional=1_000,
            )
        )


def test_equity_provider_rejects_oversized_position() -> None:
    class TradingClient:
        def get_asset(self, symbol: str):
            return SimpleNamespace(tradable=True)

        def get_account(self):
            return SimpleNamespace(buying_power="100000", equity="10000", last_equity="10000")

        def get_all_positions(self):
            return []

        def submit_order(self, request):
            raise AssertionError("Order must not be submitted")

    service = AlpacaService(settings())
    service._trading = lambda mode: TradingClient()
    service.snapshot = lambda symbol: {
        "symbol": symbol,
        "current_price": 200,
        "daily": {"volume": 5_000_000, "high": 201, "low": 199, "close": 200},
    }
    with pytest.raises(ValueError, match="position"):
        service.submit_equity_order(
            EquityOrderRequest(
                mode="paper",
                symbol="AAPL",
                side="buy",
                notional=2_000,
            )
        )
