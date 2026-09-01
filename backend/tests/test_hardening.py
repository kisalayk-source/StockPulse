from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import reset_db_state
from app.dependencies import Services
from app.main import create_app
from app.schemas import EquityOrderRequest, OptionOrderRequest
from app.services.providers import AlpacaService, option_underlying_symbol
from app.services.research import round_trip_cost
from app.services.risk import check_order_risk, spread_bps


class StubAlpaca:
    def account(self, mode: str) -> dict:
        return {"mode": mode}


class StubKronos:
    loaded = False

    def forecast(self, symbol, preset, timeframe, context, horizon, bars=None, use_cache=True, evaluate=True, engine="kronos") -> dict:
        return {"symbol": symbol.upper(), "model": {"engine": engine}}

    def scan_movers(self, limit: int = 50, refresh: bool = False) -> dict:
        return {"movers": [], "status": "ready", "scanned": 0}


def _settings(**overrides) -> Settings:
    defaults = {"database_url": "sqlite://"}
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _client(settings: Settings, alpaca=None) -> TestClient:
    reset_db_state()
    services = Services(
        settings=settings,
        alpaca=alpaca or StubAlpaca(),
        finnhub=SimpleNamespace(client=None),
        kronos=StubKronos(),
        sec=SimpleNamespace(),
    )
    return TestClient(create_app(settings, services))


def _auth_headers(client: TestClient, *, with_alpaca: bool = True) -> dict[str, str]:
    email = f"user-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    if with_alpaca:
        saved = client.put(
            "/api/v1/auth/alpaca",
            headers=headers,
            json={"mode": "paper", "key_id": "PKTESTKEY123456", "secret": "secretsecret12"},
        )
        assert saved.status_code == 200, saved.text
    return headers


def test_configured_api_key_is_required_and_compared_without_leaking() -> None:
    config = _settings(api_key="correct-secret")
    with _client(config) as client:
        missing = client.get("/api/v1/ready")
        wrong = client.get("/api/v1/ready", headers={"X-API-Key": "wrong"})
        valid = client.get("/api/v1/ready", headers={"X-API-Key": "correct-secret"})
    assert missing.status_code == wrong.status_code == 401
    assert "correct-secret" not in missing.text + wrong.text
    assert valid.status_code == 200
    assert valid.json()["status"] == "ready"


def test_request_ids_are_returned_and_invalid_values_are_replaced() -> None:
    with _client(_settings()) as client:
        preserved = client.get("/api/v1/health", headers={"X-Request-ID": "test-123"})
        replaced = client.get("/api/v1/health", headers={"X-Request-ID": "bad/id"})
    assert preserved.headers["X-Request-ID"] == "test-123"
    assert replaced.headers["X-Request-ID"] != "bad/id"


def test_provider_exception_response_is_generic() -> None:
    class BrokenAlpaca:
        def __init__(self) -> None:
            self.calls = 0

        def account(self, mode: str) -> dict:
            self.calls += 1
            if self.calls == 1:
                return {"mode": mode, "id": "acct"}
            raise RuntimeError("upstream leaked secret")

    with _client(_settings(), BrokenAlpaca()) as client:
        headers = _auth_headers(client)
        response = client.get("/api/v1/account", params={"mode": "paper"}, headers=headers)
    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed"
    assert "leaked secret" not in response.text


def test_forecast_rate_limit_is_enforced_without_external_dependency() -> None:
    config = _settings(forecast_rate_limit_per_minute=1)
    with _client(config) as client:
        headers = _auth_headers(client, with_alpaca=False)
        first = client.post("/api/v1/forecast", json={"symbol": "AAPL"}, headers=headers)
        second = client.post("/api/v1/forecast", json={"symbol": "AAPL"}, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "60"


def test_movers_scan_does_not_consume_ticker_forecast_quota() -> None:
    config = _settings(forecast_rate_limit_per_minute=1)
    with _client(config) as client:
        headers = _auth_headers(client, with_alpaca=False)
        movers = client.post(
            "/api/v1/forecast/movers", json={"refresh": True, "limit": 3}, headers=headers
        )
        forecast = client.post("/api/v1/forecast", json={"symbol": "AAPL"}, headers=headers)
    assert movers.status_code == 200
    assert forecast.status_code == 200


def test_private_network_cors_is_not_allowed_by_default() -> None:
    with _client(_settings()) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://192.168.1.20:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in response.headers


def test_spread_requires_quote_and_range_estimator_uses_basis_points() -> None:
    assert spread_bps({"daily": {"high": 101, "low": 99, "close": 100}}) is None
    bars = [
        {"close": 100, "high": 100.05, "low": 99.95, "volume": 1_000_000}
        for _ in range(6)
    ]
    assert round_trip_cost(bars)["spread_bps"] == pytest.approx(10.0)


def test_equity_sell_cannot_exceed_long_position_by_default() -> None:
    config = _settings()
    order = EquityOrderRequest(mode="paper", symbol="AAPL", side="sell", qty=2)
    with pytest.raises(ValueError, match="short selling is disabled"):
        check_order_risk(
            order,
            account={"equity": 10_000, "last_equity": 10_000, "buying_power": 10_000},
            positions=[{"symbol": "AAPL", "qty": "1", "market_value": "200"}],
            snapshot={"symbol": "AAPL"},
            settings=config,
        )


def test_option_intent_is_explicit_and_underlying_has_occ_fallback() -> None:
    assert option_underlying_symbol(SimpleNamespace(), "AAPL260821C00200000") == "AAPL"
    with pytest.raises(ValueError, match="side must match"):
        OptionOrderRequest(
            mode="paper",
            contract_symbol="AAPL260821C00200000",
            side="sell",
            qty=1,
            position_intent="buy_to_close",
        )

    class TradingClient:
        submitted = None

        def get_option_contract(self, symbol: str):
            return SimpleNamespace(tradable=True, underlying_asset=SimpleNamespace(symbol="AAPL"))

        def get_account(self):
            return SimpleNamespace(equity="100000", last_equity="100000", buying_power="50000")

        def get_all_positions(self):
            return [{"symbol": "AAPL260821C00200000", "qty": "-2", "market_value": "-500"}]

        def submit_order(self, request):
            self.submitted = request
            return SimpleNamespace(id="option-order")

    client = TradingClient()
    service = AlpacaService(_settings())
    service._trading = lambda mode: client
    service.option_snapshot = lambda contract, underlying: {
        "symbol": underlying,
        "contract_symbol": contract,
    }
    service.submit_option_order(
        OptionOrderRequest(
            mode="paper",
            contract_symbol="AAPL260821C00200000",
            side="buy",
            qty=1,
            position_intent="buy_to_close",
        )
    )
    assert client.submitted.position_intent.value == "buy_to_close"
