"""Trading agent lifecycle and paper execution tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import reset_db_state
from app.dependencies import Services
from app.main import create_app
from app.trading_agent.broker import OrderRequest, PaperBrokerAdapter
from app.trading_agent.forecast_provider import StaticForecastProvider
from app.trading_agent.risk_engine import ForecastResult
from app.trading_agent.service import TradingAgentService
from test_api import FakeAlpaca, FakeFinnhub, FakeKronos, FakeSec


def settings(**overrides) -> Settings:
    defaults = {
        "database_url": "sqlite://",
        "app_environment": "test",
        "api_key": None,
        "prediction_enabled": False,
        "sec_enabled": False,
        "sec_scan_on_startup": False,
        "allow_live_trading": False,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def make_agent_client():
    reset_db_state()
    forecast = StaticForecastProvider(
        {
            "NVDA": ForecastResult(
                symbol="NVDA",
                signal="BUY",
                confidence=0.82,
                forecast_horizon="5d",
                expected_return=0.04,
                downside_risk=0.01,
                forecast_version="test",
                generated_at=datetime.now(timezone.utc).isoformat(),
                features_snapshot_id="snap1",
                model_name="static",
            )
        }
    )
    config = settings()
    paper_brokers: dict[int, PaperBrokerAdapter] = {}
    agent = TradingAgentService(
        forecast_provider=forecast,
        alpaca=FakeAlpaca(),
        paper_brokers=paper_brokers,
        settings=config,
    )
    services = Services(config, FakeAlpaca(), FakeFinnhub(), FakeKronos(), FakeSec(), None, agent)
    client = TestClient(create_app(config, services))
    return client, agent, paper_brokers


def register_headers(client: TestClient) -> dict[str, str]:
    email = f"agent-{uuid4().hex[:8]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_agent_starts_in_paper_mode():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        resp = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "paper"
        assert data["mode"] == "paper"
        assert data["live_trading_enabled"] is False


def test_cannot_start_live_without_enablement():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        resp = client.post(
            "/api/v1/trading-agent/start",
            json={"mode": "live", "live_confirmation": "LIVE"},
            headers=headers,
        )
        assert resp.status_code == 400


def test_cannot_arm_live_when_server_disallows():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        resp = client.put(
            "/api/v1/trading-agent/config",
            json={"live_trading_enabled": True, "live_confirmation": "LIVE"},
            headers=headers,
        )
        assert resp.status_code == 422
        assert "disabled" in resp.json()["detail"].lower()


def test_paper_today_realized_ignores_prior_session_gains():
    broker = PaperBrokerAdapter(starting_cash=10_000, prices={"NVDA": 100})
    buy = broker.submit_order(OrderRequest(symbol="NVDA", side="buy", quantity=5, idempotency_key="b1"))
    assert buy.status == "filled"
    broker.set_price("NVDA", 110)
    sell = broker.submit_order(OrderRequest(symbol="NVDA", side="sell", quantity=5, idempotency_key="s1"))
    assert sell.status == "filled"
    assert broker.realized_pnl == 50
    broker.mark_day_start()
    broker.set_price("NVDA", 100)
    broker.submit_order(OrderRequest(symbol="NVDA", side="buy", quantity=2, idempotency_key="b2"))
    broker.set_price("NVDA", 90)
    broker.submit_order(OrderRequest(symbol="NVDA", side="sell", quantity=2, idempotency_key="s2"))
    assert broker.realized_pnl == 30  # lifetime
    assert broker.today_realized_pnl() == -20  # today only


def test_pause_resume_and_emergency_stop():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        assert client.post("/api/v1/trading-agent/pause", headers=headers).json()["status"] == "paused"
        assert client.post("/api/v1/trading-agent/resume", headers=headers).json()["status"] == "paper"
        assert client.post("/api/v1/trading-agent/emergency-stop", headers=headers).json()["status"] == "emergency_stop"
        cycle = client.post("/api/v1/trading-agent/cycle", json={"symbols": ["NVDA"]}, headers=headers)
        assert cycle.status_code == 400


def test_paper_cycle_stores_forecast_snapshot():
    client, agent, paper_brokers = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "long_term", "universe": ["NVDA"], "capital_allocation": 10000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        broker = paper_brokers[cfg["id"]]
        broker.set_price("NVDA", 180.0)
        cycle = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA"], "execute": True},
            headers=headers,
        )
        assert cycle.status_code == 200, cycle.text
        body = cycle.json()
        assert "run_id" in body
        candidates = client.get("/api/v1/trading-agent/candidates", headers=headers).json()["candidates"]
        assert candidates
        assert candidates[0]["forecast_snapshot"]["symbol"] == "NVDA"
        assert candidates[0]["forecast_snapshot"]["signal"] == "BUY"
        orders = client.get("/api/v1/trading-agent/orders", headers=headers).json()["orders"]
        assert orders
        assert orders[0]["status"] == "filled"


def test_duplicate_orders_prevented():
    client, agent, _ = make_agent_client()
    with client:
        headers = register_headers(client)
        # Bootstrap config via API
        client.get("/api/v1/trading-agent/config", headers=headers)
        from app.db import _SessionLocal
        from app.trading_agent.models import AgentOrder, AgentRun, TradeCandidate, TradePlan

        session = _SessionLocal()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        config.status = "paper"
        config.mode = "paper"
        config.enabled = True
        session.flush()
        run = AgentRun(agent_config_id=config.id, status="running")
        session.add(run)
        session.flush()
        tc = TradeCandidate(
            agent_run_id=run.id,
            symbol="NVDA",
            asset_type="equity",
            strategy="buy_and_hold",
            forecast_snapshot={"symbol": "NVDA", "signal": "BUY"},
            status="approved",
        )
        session.add(tc)
        session.flush()
        plan = TradePlan(
            trade_candidate_id=tc.id,
            entry_price=180,
            position_size=1,
            status="approved",
            plan_payload={},
        )
        session.add(plan)
        session.flush()
        key = "dup-key-1"
        session.add(
            AgentOrder(
                trade_plan_id=plan.id,
                broker_order_id="paper-1",
                idempotency_key=key,
                status="filled",
                side="buy",
                symbol="NVDA",
                requested_quantity=1,
                filled_quantity=1,
                average_fill_price=180,
            )
        )
        session.commit()
        result = agent._submit_plan(
            session,
            config,
            plan,
            SimpleNamespace(symbol="NVDA", side="buy", asset_type="equity"),
            key,
        )
        assert result.get("duplicate") is True
        session.close()


def test_rejected_broker_order_does_not_create_filled_position():
    paper_broker = PaperBrokerAdapter(starting_cash=100)
    paper_broker.set_price("NVDA", 500)
    result = paper_broker.submit_order(
        OrderRequest(symbol="NVDA", side="buy", quantity=1, idempotency_key="r1")
    )
    assert result.status == "rejected"
    assert paper_broker.get_positions() == []


def test_sell_quantity_capped_to_held_shares():
    paper_broker = PaperBrokerAdapter(starting_cash=10_000, prices={"NVDA": 100})
    buy = paper_broker.submit_order(
        OrderRequest(symbol="NVDA", side="buy", quantity=5, idempotency_key="b1")
    )
    assert buy.status == "filled"
    sell = paper_broker.submit_order(
        OrderRequest(symbol="NVDA", side="sell", quantity=10, idempotency_key="s1")
    )
    assert sell.status == "filled"
    assert sell.filled_quantity == 5
    assert paper_broker.get_positions() == []


def test_daily_loss_reset_endpoint_and_restart_does_not_reset():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        before = client.get("/api/v1/trading-agent/daily-loss", headers=headers).json()
        client.post("/api/v1/trading-agent/pause", headers=headers)
        client.post("/api/v1/trading-agent/resume", headers=headers)
        after_pause = client.get("/api/v1/trading-agent/daily-loss", headers=headers).json()
        assert after_pause["trading_date"] == before["trading_date"]
        assert after_pause["starting_equity"] == before["starting_equity"]

        client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        after_restart = client.get("/api/v1/trading-agent/daily-loss", headers=headers).json()
        assert after_restart["trading_date"] == before["trading_date"]
        assert after_restart["starting_equity"] == before["starting_equity"]

        reset = client.post("/api/v1/trading-agent/daily-loss/reset", headers=headers)
        assert reset.status_code == 200
        assert reset.json()["status"] == "active"


def test_risk_management_endpoints():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        got = client.get("/api/v1/risk-management/config", headers=headers)
        assert got.status_code == 200
        assert "profiles" in got.json()
        updated = client.put(
            "/api/v1/risk-management/config",
            json={"risk_profile": "low"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["risk_profile"] == "low"
        assert updated.json()["risk_config"]["max_position_size_pct"] == 0.05


def test_max_daily_loss_config_roundtrip():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        resp = client.put(
            "/api/v1/trading-agent/daily-loss",
            json={
                "max_daily_loss_enabled": True,
                "max_daily_loss_amount": 500,
                "max_daily_loss_percent": 2,
                "daily_loss_calculation": "realized_plus_unrealized_plus_fees",
                "daily_loss_reset_time": "00:00",
                "daily_loss_timezone": "America/Los_Angeles",
                "daily_loss_action": "cancel_orders_and_pause",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        cfg = client.get("/api/v1/trading-agent/config", headers=headers).json()
        assert cfg["risk_config"]["max_daily_loss_amount"] == 500
        assert cfg["daily_loss"]["effective_limit"] is not None
