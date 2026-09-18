"""Trading agent lifecycle and paper execution tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from app.trading_agent.models import AgentOrder, AgentPosition, AgentRun, TradeCandidate, TradePlan
from app.trading_agent.service import TradingAgentService
from app.trading_agent.strategies import DayTradingStrategy, build_intraday_exit_candidates
from test_api import FakeAlpaca, FakeFinnhub, FakeKronos, FakeSec


def _db_session():
    from app.db import _SessionLocal

    assert _SessionLocal is not None
    return _SessionLocal()


def _seed_open_long_plan(
    session,
    *,
    config,
    quantity: float = 5,
    entry_price: float = 100,
    stop_loss: float | None = 95,
    take_profit: float | None = 110,
    opened_at: datetime | None = None,
    strategy: str = "intraday_momentum",
) -> None:
    run = AgentRun(agent_config_id=config.id, status="completed", forecast_version="seed")
    session.add(run)
    session.flush()
    tc = TradeCandidate(
        agent_run_id=run.id,
        symbol="NVDA",
        asset_type="equity",
        strategy=strategy,
        forecast_snapshot={"signal": "BUY"},
        status="approved",
    )
    session.add(tc)
    session.flush()
    mode = "long_term" if strategy == "buy_and_hold" else "day_trading"
    session.add(
        TradePlan(
            trade_candidate_id=tc.id,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=quantity,
            status="executed",
            plan_payload={"symbol": "NVDA", "mode": mode, "strategy": strategy},
        )
    )
    session.add(
        AgentPosition(
            user_id=config.user_id,
            agent_config_id=config.id,
            symbol="NVDA",
            asset_type="equity",
            quantity=quantity,
            average_entry_price=entry_price,
            current_price=entry_price,
            opened_at=opened_at or (datetime.now(timezone.utc) - timedelta(minutes=10)),
        )
    )
    session.commit()


def _seed_filled_order(
    session,
    *,
    config,
    symbol: str = "NVDA",
    side: str = "buy",
    quantity: float = 5,
    price: float = 100,
    filled_at: datetime | None = None,
    strategy: str = "long_equity",
    asset_type: str = "equity",
) -> AgentOrder:
    when = filled_at or datetime.now(timezone.utc)
    run = AgentRun(agent_config_id=config.id, status="completed", forecast_version="day-trades")
    session.add(run)
    session.flush()
    tc = TradeCandidate(
        agent_run_id=run.id,
        symbol=symbol,
        asset_type=asset_type,
        strategy=strategy,
        forecast_snapshot={"signal": "BUY" if side == "buy" else "SELL"},
        status="approved",
    )
    session.add(tc)
    session.flush()
    plan = TradePlan(
        trade_candidate_id=tc.id,
        entry_price=price,
        position_size=quantity,
        status="executed",
        plan_payload={"symbol": symbol, "strategy": strategy},
    )
    session.add(plan)
    session.flush()
    order = AgentOrder(
        trade_plan_id=plan.id,
        broker_order_id=f"seed-{uuid4().hex[:8]}",
        idempotency_key=f"day-trade-{uuid4().hex}",
        status="filled",
        submitted_at=when,
        filled_at=when,
        filled_quantity=quantity,
        average_fill_price=price,
        side=side,
        order_type="market",
        requested_quantity=quantity,
        symbol=symbol,
    )
    session.add(order)
    session.flush()
    return order


def settings(**overrides) -> Settings:
    defaults = {
        "database_url": "sqlite://",
        "app_environment": "test",
        "api_key": None,
        "prediction_enabled": False,
        "sec_enabled": False,
        "sec_scan_on_startup": False,
        "allow_live_trading": False,
        "agent_scheduler_enabled": False,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def make_agent_client(*, use_alpaca: bool = False):
    """Build a test client.

    ``use_alpaca=False`` keeps the in-memory PaperBrokerAdapter (strategy unit tests).
    ``use_alpaca=True`` routes paper mode through FakeAlpaca like production.
    """
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
    alpaca = FakeAlpaca() if use_alpaca else None
    agent = TradingAgentService(
        forecast_provider=forecast,
        alpaca=alpaca,
        paper_brokers=paper_brokers,
        settings=config,
    )
    services = Services(
        config,
        alpaca or FakeAlpaca(),
        FakeFinnhub(),
        FakeKronos(),
        FakeSec(),
        government=None,
        prediction=None,
        trading_agent=agent,
    )
    client = TestClient(create_app(config, services))
    return client, agent, paper_brokers, alpaca


def register_headers(client: TestClient, *, with_alpaca: bool = False) -> dict[str, str]:
    email = f"agent-{uuid4().hex[:8]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
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


def test_agent_starts_in_paper_mode():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        resp = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "paper"
        assert data["mode"] == "paper"
        assert data["live_trading_enabled"] is False


def test_new_agent_uses_default_universe():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        data = client.get("/api/v1/trading-agent/config", headers=headers).json()
        assert data["universe"] == ["SPY", "AAPL", "MSFT", "NVDA", "AMZN"]


def test_universe_can_be_updated_from_api():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        updated = client.put(
            "/api/v1/trading-agent/config",
            json={"universe": [" aapl ", "MSFT", "aapl", "BRK.B"]},
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["universe"] == ["AAPL", "MSFT", "BRK.B"]


def test_universe_rejects_invalid_or_empty_tickers():
    with make_agent_client()[0] as client:
        headers = register_headers(client)
        empty = client.put(
            "/api/v1/trading-agent/config",
            json={"universe": []},
            headers=headers,
        )
        assert empty.status_code == 422
        bad = client.put(
            "/api/v1/trading-agent/config",
            json={"universe": ["NOPE!"]},
            headers=headers,
        )
        assert bad.status_code == 422


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
    client, agent, paper_brokers, _alpaca = make_agent_client()
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




def test_paper_mode_routes_orders_to_alpaca():
    client, agent, paper_brokers, alpaca = make_agent_client(use_alpaca=True)
    assert alpaca is not None
    with client:
        headers = register_headers(client, with_alpaca=True)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "long_term", "universe": ["NVDA"], "capital_allocation": 10000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        assert cfg["id"] not in paper_brokers
        cycle = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA"], "execute": True},
            headers=headers,
        )
        assert cycle.status_code == 200, cycle.text
        assert alpaca.submitted, "expected agent orders to hit FakeAlpaca"
        orders = client.get("/api/v1/trading-agent/orders", headers=headers).json()["orders"]
        assert orders
        assert orders[0]["status"] == "filled"


def test_paper_start_requires_alpaca_credentials_when_broker_configured():
    client, _agent, _paper, _alpaca = make_agent_client(use_alpaca=True)
    with client:
        headers = register_headers(client, with_alpaca=False)
        resp = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        assert resp.status_code == 400
        assert "alpaca" in resp.json()["detail"].lower()


def test_config_loads_with_alpaca_credentials_bound():
    client, _agent, _paper, _alpaca = make_agent_client(use_alpaca=True)
    with client:
        headers = register_headers(client, with_alpaca=True)
        resp = client.get("/api/v1/trading-agent/config", headers=headers)
        assert resp.status_code == 200, resp.text
        assert "daily_loss" in resp.json()
        assert "current_equity" in resp.json()["daily_loss"]
        perf = client.get("/api/v1/trading-agent/performance", headers=headers)
        assert perf.status_code == 200, perf.text
        assert "total_pnl" in perf.json()
        positions = client.get("/api/v1/trading-agent/positions", headers=headers)
        assert positions.status_code == 200, positions.text


def test_config_payload_soft_fails_on_provider_unavailable():
    from app.services.providers import ProviderUnavailable

    client, agent, _paper, _alpaca = make_agent_client(use_alpaca=True)
    with client:
        headers = register_headers(client, with_alpaca=True)
        me = client.get("/api/v1/auth/me", headers=headers).json()
        session = _db_session()
        config = agent.get_or_create_config(session, me["id"])

        def boom(*_args, **_kwargs):
            raise ProviderUnavailable("alpaca", "Alpaca paper credentials are not configured")

        agent.get_daily_loss_snapshot = boom  # type: ignore[method-assign]
        payload = agent.config_payload(session, config)
        warnings = payload["daily_loss"].get("warnings") or []
        assert any("credential" in str(w).lower() for w in warnings)
        session.close()


def test_duplicate_orders_prevented():
    client, agent, _paper_brokers, _alpaca = make_agent_client()
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
        assert "max_trades_per_day" in cfg["daily_loss"]
        assert "trades_today" in cfg["daily_loss"]
        assert cfg["daily_loss"]["max_trades_per_day"] == cfg["risk_config"]["max_trades_per_day"]
        assert cfg["daily_loss"]["trades_today"] >= 0


def test_daily_loss_includes_trades_today_after_fill():
    client, agent, paper_brokers, _alpaca = make_agent_client()
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
        daily = client.get("/api/v1/trading-agent/daily-loss", headers=headers).json()
        assert daily["trades_today"] >= 1
        assert daily["max_trades_per_day"] == cfg["risk_config"]["max_trades_per_day"]


def _forecast(signal: str, *, expected_return: float = 0.03) -> ForecastResult:
    return ForecastResult(
        symbol="NVDA",
        signal=signal,
        confidence=0.85,
        forecast_horizon="1Day",
        expected_return=expected_return,
        downside_risk=0.01,
        forecast_version="test",
        generated_at=datetime.now(timezone.utc).isoformat(),
        features_snapshot_id="snap1",
        model_name="static",
    )


def test_day_trading_sell_uses_held_quantity_not_budget():
    strategy = DayTradingStrategy()
    risk = {
        "allow_day_trading": True,
        "max_position_size_pct": 0.5,
        "short_selling_enabled": False,
        "default_stop_loss_pct": 0.01,
        "default_take_profit_pct": 0.02,
    }
    sells = strategy.generate(
        "NVDA", _forecast("SELL", expected_return=-0.03), 100.0, risk, 50_000, held_qty=4
    )
    assert len(sells) == 1
    assert sells[0].side == "sell"
    assert sells[0].quantity == 4
    assert (
        strategy.generate(
            "NVDA", _forecast("SELL", expected_return=-0.03), 100.0, risk, 50_000, held_qty=0
        )
        == []
    )


def test_intraday_exit_triggers_for_stop_take_hold_and_eod():
    now = datetime(2026, 9, 10, 19, 50, tzinfo=timezone.utc)
    risk = {
        "max_position_holding_minutes": 30,
        "min_exit_holding_minutes": 0,
        "close_positions_before_market_close": True,
    }
    stop = build_intraday_exit_candidates(
        symbol="NVDA",
        quantity=5,
        mark_price=94,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        opened_at=now - timedelta(minutes=5),
        risk_config=risk,
        now=now,
    )
    assert stop and stop[0].metadata["exit_reason"] == "stop_loss"
    assert stop[0].quantity == 5

    gated = build_intraday_exit_candidates(
        symbol="NVDA",
        quantity=5,
        mark_price=94,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        opened_at=now - timedelta(minutes=5),
        risk_config={**risk, "min_exit_holding_minutes": 30},
        now=now,
    )
    assert gated == []

    take = build_intraday_exit_candidates(
        symbol="NVDA",
        quantity=5,
        mark_price=111,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        opened_at=now - timedelta(minutes=5),
        risk_config=risk,
        now=now,
    )
    assert take and take[0].metadata["exit_reason"] == "take_profit"

    held = build_intraday_exit_candidates(
        symbol="NVDA",
        quantity=5,
        mark_price=101,
        entry_price=100,
        stop_loss=90,
        take_profit=120,
        opened_at=now - timedelta(minutes=45),
        risk_config={**risk, "max_holding_enabled": True},
        now=now,
    )
    assert held and held[0].metadata["exit_reason"] == "max_holding"

    skipped_hold = build_intraday_exit_candidates(
        symbol="NVDA",
        quantity=5,
        mark_price=101,
        entry_price=100,
        stop_loss=90,
        take_profit=120,
        opened_at=now - timedelta(minutes=45),
        risk_config=risk,
        now=now,
    )
    assert skipped_hold == []

    eod = build_intraday_exit_candidates(
        symbol="NVDA",
        quantity=5,
        mark_price=101,
        entry_price=100,
        stop_loss=90,
        take_profit=120,
        opened_at=now - timedelta(minutes=5),
        risk_config={**risk, "min_exit_holding_minutes": 30},
        now=now,
        near_close=True,
    )
    assert eod and eod[0].metadata["exit_reason"] == "eod_flatten"


def test_legacy_max_holding_minutes_do_not_force_exits():
    from app.trading_agent.risk_profiles import get_risk_config, merge_risk_config

    now = datetime(2026, 9, 10, 19, 50, tzinfo=timezone.utc)
    risk = merge_risk_config(get_risk_config("medium"), {"max_position_holding_minutes": 240})
    assert risk["max_holding_enabled"] is False
    exits = build_intraday_exit_candidates(
        symbol="NVDA",
        quantity=5,
        mark_price=101,
        entry_price=100,
        stop_loss=90,
        take_profit=120,
        opened_at=now - timedelta(hours=5),
        risk_config=risk,
        now=now,
    )
    assert exits == []


def _start_day_trading_with_long(agent, paper_brokers, client, headers, *, qty: float = 5, price: float = 100.0):
    client.put(
        "/api/v1/trading-agent/config",
        json={"trading_type": "day_trading", "universe": ["NVDA"], "capital_allocation": 10_000},
        headers=headers,
    )
    cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
    broker = paper_brokers[cfg["id"]]
    broker.set_price("NVDA", price)
    buy = broker.submit_order(
        OrderRequest(symbol="NVDA", side="buy", quantity=qty, idempotency_key=f"entry-{uuid4().hex[:8]}")
    )
    assert buy.status == "filled"
    session = _db_session()
    me = client.get("/api/v1/auth/me", headers=headers).json()
    config = agent.get_or_create_config(session, me["id"])
    return session, config, broker


def test_cycle_sells_open_long_when_stop_is_hit():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider({"NVDA": _forecast("HOLD", expected_return=0.0)})
    with client:
        headers = register_headers(client)
        session, config, broker = _start_day_trading_with_long(agent, paper_brokers, client, headers)
        risk = dict(agent.resolved_risk_config(config))
        risk["min_exit_holding_minutes"] = 0
        config.risk_config = risk
        session.commit()
        _seed_open_long_plan(session, config=config, stop_loss=95, take_profit=110)

        broker.set_price("NVDA", 94.0)
        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 94.0},
        )
        session.commit()
        sell_orders = [row for row in result["approved"] if row["strategy"] == "intraday_exit"]
        assert sell_orders, result
        assert sell_orders[0]["metadata"]["exit_reason"] == "stop_loss"
        listed = [c for c in agent.list_candidates(session, config) if c["strategy"] == "intraday_exit"]
        assert listed and listed[0]["exit_reason"] == "stop_loss"
        assert listed[0]["forecast_snapshot"].get("exit_reason") == "stop_loss"
        assert broker.get_positions() == []
        session.close()


def test_cycle_sells_open_long_when_take_profit_is_hit():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider({"NVDA": _forecast("HOLD", expected_return=0.0)})
    with client:
        headers = register_headers(client)
        session, config, broker = _start_day_trading_with_long(agent, paper_brokers, client, headers)
        risk = dict(agent.resolved_risk_config(config))
        risk["min_exit_holding_minutes"] = 0
        config.risk_config = risk
        session.commit()
        _seed_open_long_plan(session, config=config, stop_loss=95, take_profit=110)

        broker.set_price("NVDA", 111.0)
        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 111.0},
        )
        session.commit()
        sell_orders = [row for row in result["approved"] if row["strategy"] == "intraday_exit"]
        assert sell_orders, result
        assert sell_orders[0]["metadata"]["exit_reason"] == "take_profit"
        assert broker.get_positions() == []
        session.close()


def test_cycle_sells_when_max_holding_minutes_elapsed():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider({"NVDA": _forecast("HOLD", expected_return=0.0)})
    with client:
        headers = register_headers(client)
        session, config, broker = _start_day_trading_with_long(agent, paper_brokers, client, headers)
        risk = dict(agent.resolved_risk_config(config))
        risk["max_holding_enabled"] = True
        risk["max_position_holding_minutes"] = 30
        risk["close_positions_before_market_close"] = False
        config.risk_config = risk
        session.commit()
        _seed_open_long_plan(
            session,
            config=config,
            stop_loss=50,
            take_profit=200,
            opened_at=datetime.now(timezone.utc) - timedelta(minutes=45),
        )

        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 100.0},
            near_close=False,
        )
        session.commit()
        sell_orders = [row for row in result["approved"] if row["strategy"] == "intraday_exit"]
        assert sell_orders, result
        assert sell_orders[0]["metadata"]["exit_reason"] == "max_holding"
        assert broker.get_positions() == []
        session.close()


def test_cycle_does_not_sell_when_max_holding_is_disabled():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider({"NVDA": _forecast("HOLD", expected_return=0.0)})
    with client:
        headers = register_headers(client)
        session, config, broker = _start_day_trading_with_long(agent, paper_brokers, client, headers)
        risk = dict(agent.resolved_risk_config(config))
        risk["max_holding_enabled"] = False
        risk["max_position_holding_minutes"] = 30
        risk["close_positions_before_market_close"] = False
        config.risk_config = risk
        session.commit()
        _seed_open_long_plan(
            session,
            config=config,
            stop_loss=50,
            take_profit=200,
            opened_at=datetime.now(timezone.utc) - timedelta(minutes=45),
        )

        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 100.0},
            near_close=False,
        )
        session.commit()
        sell_orders = [row for row in result["approved"] if row["strategy"] == "intraday_exit"]
        assert sell_orders == []
        assert broker.get_positions(), "position should remain open when max holding is off"
        session.close()


def test_cycle_sells_near_market_close():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider({"NVDA": _forecast("HOLD", expected_return=0.0)})
    with client:
        headers = register_headers(client)
        session, config, broker = _start_day_trading_with_long(agent, paper_brokers, client, headers)
        risk = dict(agent.resolved_risk_config(config))
        risk["max_position_holding_minutes"] = 0
        risk["close_positions_before_market_close"] = True
        config.risk_config = risk
        session.commit()
        _seed_open_long_plan(session, config=config, stop_loss=50, take_profit=200)

        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 100.0},
            near_close=True,
        )
        session.commit()
        sell_orders = [row for row in result["approved"] if row["strategy"] == "intraday_exit"]
        assert sell_orders, result
        assert sell_orders[0]["metadata"]["exit_reason"] == "eod_flatten"
        assert broker.get_positions() == []
        session.close()


def test_cycle_does_not_intraday_exit_buy_and_hold_on_stop():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider({"NVDA": _forecast("HOLD", expected_return=0.0)})
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "long_term", "universe": ["NVDA"], "capital_allocation": 10_000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        broker = paper_brokers[cfg["id"]]
        broker.set_price("NVDA", 100.0)
        buy = broker.submit_order(
            OrderRequest(symbol="NVDA", side="buy", quantity=5, idempotency_key=f"bh-{uuid4().hex[:8]}")
        )
        assert buy.status == "filled"
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        risk = dict(agent.resolved_risk_config(config))
        risk["min_exit_holding_minutes"] = 0
        config.risk_config = risk
        session.commit()
        _seed_open_long_plan(
            session,
            config=config,
            stop_loss=95,
            take_profit=110,
            strategy="buy_and_hold",
            opened_at=datetime.now(timezone.utc) - timedelta(minutes=45),
        )
        broker.set_price("NVDA", 94.0)
        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 94.0},
        )
        session.commit()
        exits = [row for row in result["approved"] if row["strategy"] == "intraday_exit"]
        assert exits == [], result
        assert broker.get_positions()
        session.close()


def test_cycle_respects_min_exit_holding_before_stop():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider({"NVDA": _forecast("HOLD", expected_return=0.0)})
    with client:
        headers = register_headers(client)
        session, config, broker = _start_day_trading_with_long(agent, paper_brokers, client, headers)
        risk = dict(agent.resolved_risk_config(config))
        risk["min_exit_holding_minutes"] = 30
        risk["close_positions_before_market_close"] = False
        config.risk_config = risk
        session.commit()
        _seed_open_long_plan(
            session,
            config=config,
            stop_loss=95,
            take_profit=110,
            opened_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        broker.set_price("NVDA", 94.0)
        blocked = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 94.0},
            near_close=False,
        )
        session.commit()
        assert [r for r in blocked["approved"] if r["strategy"] == "intraday_exit"] == [], blocked

        pos = (
            session.query(AgentPosition)
            .filter(AgentPosition.agent_config_id == config.id, AgentPosition.symbol == "NVDA")
            .order_by(AgentPosition.id.desc())
            .first()
        )
        assert pos is not None
        pos.opened_at = datetime.now(timezone.utc) - timedelta(minutes=45)
        session.commit()

        broker.set_price("NVDA", 94.0)
        allowed = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 94.0},
            near_close=False,
        )
        session.commit()
        sells = [r for r in allowed["approved"] if r["strategy"] == "intraday_exit"]
        assert sells, allowed
        assert sells[0]["metadata"]["exit_reason"] == "stop_loss"
        session.close()


def test_mixed_cycle_approves_only_one_buy_per_symbol():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "mixed", "universe": ["NVDA"], "capital_allocation": 10_000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        broker = paper_brokers[cfg["id"]]
        broker.set_price("NVDA", 180.0)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 180.0},
        )
        session.commit()
        buys = [
            row
            for row in result["approved"]
            if row["strategy"] in {"buy_and_hold", "intraday_momentum"}
        ]
        assert len(buys) == 1, result
        session.close()


def test_cycle_forecast_sell_closes_held_shares():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider(
        {"NVDA": _forecast("SELL", expected_return=-0.04)}
    )
    with client:
        headers = register_headers(client)
        session, config, broker = _start_day_trading_with_long(
            agent, paper_brokers, client, headers, qty=3
        )
        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 100.0},
            near_close=False,
        )
        session.commit()
        sells = [
            row
            for row in result["approved"]
            if row.get("order") and row["strategy"] == "intraday_momentum"
        ]
        assert sells, result
        assert broker.get_positions() == []
        session.close()


def test_trades_today_ignores_prior_session_fills():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "day_trading", "universe": ["NVDA"], "capital_allocation": 10_000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        broker = paper_brokers[cfg["id"]]

        run = AgentRun(agent_config_id=config.id, status="completed", forecast_version="old")
        session.add(run)
        session.flush()
        tc = TradeCandidate(
            agent_run_id=run.id,
            symbol="NVDA",
            asset_type="equity",
            strategy="intraday_momentum",
            forecast_snapshot={},
            status="approved",
        )
        session.add(tc)
        session.flush()
        plan = TradePlan(
            trade_candidate_id=tc.id,
            entry_price=100,
            position_size=1,
            status="executed",
            plan_payload={},
        )
        session.add(plan)
        session.flush()
        session.add(
            AgentOrder(
                trade_plan_id=plan.id,
                broker_order_id="old-1",
                idempotency_key=f"old-{uuid4().hex}",
                status="filled",
                submitted_at=datetime.now(timezone.utc) - timedelta(days=2),
                filled_at=datetime.now(timezone.utc) - timedelta(days=2),
                filled_quantity=1,
                average_fill_price=100,
                side="buy",
                order_type="market",
                requested_quantity=1,
                symbol="NVDA",
            )
        )
        session.commit()

        snap = agent._portfolio_snapshot(session, config, broker)
        assert snap.trades_today == 0
        session.close()


def test_start_resets_last_cycle_at_for_auto_cycle():
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"cycle_interval_seconds": 600, "universe": ["NVDA"]},
            headers=headers,
        )
        start = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        assert start.status_code == 200
        data = start.json()
        assert data["status"] == "paper"
        assert data["cycle_interval_seconds"] == 600
        assert data["last_cycle_at"] is None

        cycle = client.post("/api/v1/trading-agent/cycle", json={"execute": True}, headers=headers)
        assert cycle.status_code == 200
        after = client.get("/api/v1/trading-agent/config", headers=headers).json()
        assert after["last_cycle_at"] is not None


def test_scheduler_selects_only_running_configs_and_respects_interval():
    from app.trading_agent.scheduler import AgentCycleScheduler

    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"universe": ["NVDA"], "cycle_interval_seconds": 300},
            headers=headers,
        )
        client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)

        scheduler = AgentCycleScheduler(SimpleNamespace(trading_agent=agent, alpaca=FakeAlpaca()), tick_seconds=60)
        cycled = scheduler.tick()
        assert len(cycled) == 1

        # Immediate second tick should skip because last_cycle_at was stamped
        skipped = scheduler.tick()
        assert skipped == []

        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        config.last_cycle_at = datetime.now(timezone.utc) - timedelta(seconds=400)
        session.commit()
        session.close()

        due_again = scheduler.tick()
        assert len(due_again) == 1


def test_scheduler_skips_paused_agent():
    from app.trading_agent.scheduler import AgentCycleScheduler

    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        client.post("/api/v1/trading-agent/pause", headers=headers)

        scheduler = AgentCycleScheduler(SimpleNamespace(trading_agent=agent, alpaca=FakeAlpaca()), tick_seconds=60)
        assert scheduler.tick() == []


def test_scheduler_overlap_guard_skips_busy_config():
    from app.trading_agent.scheduler import AgentCycleScheduler

    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        start = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        config_id = int(start["id"])

        scheduler = AgentCycleScheduler(SimpleNamespace(trading_agent=agent, alpaca=FakeAlpaca()), tick_seconds=60)
        lock = scheduler._lock_for(config_id)
        assert lock.acquire(blocking=False)
        try:
            assert scheduler.tick() == []
        finally:
            lock.release()


def test_all_rejected_cycle_auto_adjusts_risk():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={
                "trading_type": "long_term",
                "universe": ["NVDA"],
                "capital_allocation": 10_000,
                "risk_profile": "custom",
                "risk_config": {
                    "min_forecast_confidence": 0.95,
                    "min_expected_return": 0.01,
                },
            },
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        paper_brokers[cfg["id"]].set_price("NVDA", 180.0)
        cycle = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA"], "execute": True},
            headers=headers,
        )
        assert cycle.status_code == 200, cycle.text
        body = cycle.json()
        assert body.get("approved") == []
        assert body.get("rejected")
        assert body.get("auto_adjust") is not None
        assert "Loosened" in body["auto_adjust"]["message"]

        config = client.get("/api/v1/trading-agent/config", headers=headers).json()
        assert config["risk_profile"] == "custom"
        assert float(config["risk_config"]["min_forecast_confidence"]) == 0.90
        events = client.get("/api/v1/trading-agent/events", headers=headers).json()["events"]
        assert any(e["event_type"] == "RISK_AUTO_ADJUSTED" for e in events)


def test_auto_adjust_skipped_when_only_market_closed_rejects():
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "day_trading", "universe": ["NVDA"], "capital_allocation": 10_000},
            headers=headers,
        )
        client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        before_conf = float(agent.resolved_risk_config(config).get("min_forecast_confidence") or 0)
        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=False,
            market_open=False,
            prices={"NVDA": 180.0},
        )
        session.commit()
        session.close()
        assert result.get("auto_adjust") is None
        # Day trades rejected for market closed should not loosen confidence
        session = _db_session()
        config = agent.get_or_create_config(session, me["id"])
        after_conf = float(agent.resolved_risk_config(config).get("min_forecast_confidence") or 0)
        session.close()
        assert after_conf == before_conf


def test_auto_adjust_respects_daily_cap():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={
                "trading_type": "long_term",
                "universe": ["NVDA"],
                "risk_profile": "custom",
                "risk_config": {
                    "min_forecast_confidence": 0.95,
                    "min_expected_return": 0.05,
                    "auto_adjust_count": 3,
                    "auto_adjust_date": __import__("datetime").date.today().isoformat(),
                },
            },
            headers=headers,
        )
        # Fix date to trading_date_for America/Los_Angeles
        from app.trading_agent.daily_loss import trading_date_for
        from datetime import datetime, timezone

        today = trading_date_for(datetime.now(timezone.utc), "America/Los_Angeles", "00:00").isoformat()
        client.put(
            "/api/v1/trading-agent/config",
            json={
                "risk_profile": "custom",
                "risk_config": {
                    "min_forecast_confidence": 0.95,
                    "min_expected_return": 0.05,
                    "auto_adjust_count": 3,
                    "auto_adjust_date": today,
                },
            },
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        paper_brokers[cfg["id"]].set_price("NVDA", 180.0)
        cycle = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA"], "execute": True},
            headers=headers,
        )
        assert cycle.status_code == 200
        assert cycle.json().get("auto_adjust") is None
        events = client.get("/api/v1/trading-agent/events", headers=headers).json()["events"]
        assert any(e["event_type"] == "RISK_AUTO_ADJUST_SKIPPED" for e in events)


def test_paper_broker_hydrates_positions_after_restart():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "long_term", "universe": ["NVDA"], "capital_allocation": 10_000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        config_id = cfg["id"]
        paper_brokers[config_id].set_price("NVDA", 180.0)
        cycle = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA"], "execute": True},
            headers=headers,
        )
        assert cycle.status_code == 200
        assert cycle.json()["approved"]

        # Simulate API process restart: drop in-memory brokers
        paper_brokers.clear()
        agent._paper_brokers.clear()

        positions = client.get("/api/v1/trading-agent/positions", headers=headers).json()["positions"]
        assert positions
        assert positions[0]["symbol"] == "NVDA"
        assert float(positions[0]["quantity"]) > 0


def test_performance_includes_realized_pnl_after_full_exit():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "day_trading", "universe": ["NVDA"], "capital_allocation": 10_000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        broker = paper_brokers[cfg["id"]]
        broker.set_price("NVDA", 100.0)

        # Buy via cycle
        buy = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA"], "execute": True},
            headers=headers,
        )
        assert buy.status_code == 200
        assert buy.json()["approved"]
        open_pos = client.get("/api/v1/trading-agent/positions", headers=headers).json()["positions"]
        assert open_pos
        qty = float(open_pos[0]["quantity"])
        assert qty > 0

        # Force profitable exit
        broker.set_price("NVDA", 110.0)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 110.0},
            near_close=True,
        )
        session.commit()
        session.close()
        assert any(a.get("strategy") == "intraday_exit" for a in result.get("approved") or [])

        positions = client.get("/api/v1/trading-agent/positions", headers=headers).json()["positions"]
        assert positions == [] or all(float(p["quantity"]) == 0 for p in positions)

        perf = client.get("/api/v1/trading-agent/performance", headers=headers).json()
        assert float(perf["realized_pnl"]) > 0
        assert float(perf["total_pnl"]) > 0
        assert int(perf["number_of_trades"]) >= 2
        assert float(perf["proceeds_from_exits"]) > 0
        assert float(perf["capital_invested"]) == 0.0
        assert "account_equity" in perf
        assert "starting_capital" in perf
        # Paper equity change should track total P/L when marks match fills.
        assert abs(float(perf["equity_change"]) - float(perf["total_pnl"])) < 1e-6


def test_performance_capital_metrics_when_pnl_is_zero_at_flat_marks():
    """Buy and sell at the same $100 paper mark → $0 P/L but capital still moved."""
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "day_trading", "universe": ["NVDA"], "capital_allocation": 10_000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        broker = paper_brokers[cfg["id"]]
        broker.set_price("NVDA", 100.0)

        buy = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA"], "execute": True},
            headers=headers,
        )
        assert buy.status_code == 200
        assert buy.json()["approved"]
        open_pos = client.get("/api/v1/trading-agent/positions", headers=headers).json()["positions"]
        assert open_pos
        qty = float(open_pos[0]["quantity"])
        invested_while_open = client.get("/api/v1/trading-agent/performance", headers=headers).json()
        assert float(invested_while_open["capital_invested"]) == pytest.approx(qty * 100.0)
        assert float(invested_while_open["total_pnl"]) == pytest.approx(0.0)

        # Flat exit at the same mark — realized P/L stays 0, sell proceeds should still report.
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        result = agent.run_cycle(
            session,
            config,
            symbols=["NVDA"],
            execute=True,
            market_open=True,
            prices={"NVDA": 100.0},
            near_close=True,
        )
        session.commit()
        session.close()
        assert any(a.get("strategy") == "intraday_exit" for a in result.get("approved") or [])

        perf = client.get("/api/v1/trading-agent/performance", headers=headers).json()
        assert float(perf["realized_pnl"]) == pytest.approx(0.0)
        assert float(perf["total_pnl"]) == pytest.approx(0.0)
        assert float(perf["capital_invested"]) == pytest.approx(0.0)
        assert float(perf["proceeds_from_exits"]) == pytest.approx(qty * 100.0)
        assert int(perf["number_of_trades"]) >= 2


def test_max_holding_uses_latest_buy_not_stale_opened_at():
    """Rebuy after exit must not immediately flatten on next cycle via stale opened_at."""
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={
                "trading_type": "day_trading",
                "universe": ["NVDA"],
                "capital_allocation": 10_000,
                "risk_profile": "custom",
                "risk_config": {
                    "max_holding_enabled": True,
                    "max_position_holding_minutes": 240,
                    "close_positions_before_market_close": False,
                    "default_stop_loss_pct": 0.5,
                    "default_take_profit_pct": 0.5,
                    "allow_day_trading": True,
                },
            },
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        broker = paper_brokers[cfg["id"]]
        broker.set_price("NVDA", 100.0)
        broker.restore_position(
            symbol="NVDA",
            quantity=5,
            average_entry_price=100.0,
            current_price=100.0,
        )

        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        recent = datetime.now(timezone.utc) - timedelta(minutes=3)
        _seed_open_long_plan(
            session,
            config=config,
            quantity=5,
            entry_price=100,
            stop_loss=50,
            take_profit=150,
            opened_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        # Re-open session after seed commit
        session = _db_session()
        config = agent.get_or_create_config(session, me["id"])
        pos = (
            session.query(AgentPosition)
            .filter(AgentPosition.agent_config_id == config.id, AgentPosition.symbol == "NVDA")
            .one()
        )
        pos.opened_at = datetime.now(timezone.utc) - timedelta(days=1)
        plan = (
            session.query(TradePlan)
            .join(TradeCandidate)
            .join(AgentRun)
            .filter(AgentRun.agent_config_id == config.id)
            .order_by(TradePlan.id.desc())
            .first()
        )
        assert plan is not None
        session.add(
            AgentOrder(
                trade_plan_id=plan.id,
                broker_order_id=f"seed-buy-{uuid4().hex[:8]}",
                idempotency_key=f"seed-buy-{uuid4().hex}",
                status="filled",
                side="buy",
                symbol="NVDA",
                order_type="market",
                requested_quantity=5,
                filled_quantity=5,
                average_fill_price=100,
                submitted_at=recent,
                filled_at=recent,
            )
        )
        session.commit()
        session.close()

        cycle = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA"], "execute": True},
            headers=headers,
        )
        assert cycle.status_code == 200, cycle.text
        body = cycle.json()
        exit_sells = [
            a
            for a in (body.get("approved") or [])
            if a.get("strategy") == "intraday_exit" and a.get("symbol") == "NVDA"
        ]
        assert exit_sells == [], body
        positions = client.get("/api/v1/trading-agent/positions", headers=headers).json()["positions"]
        assert any(p["symbol"] == "NVDA" and float(p["quantity"]) > 0 for p in positions)


def test_provider_uses_hybrid_signal_and_path_expected_return():
    from app.trading_agent.forecast_provider import KronosForecastProvider

    class FakePrediction:
        def predict(self, ticker, horizon="5d"):
            return {
                "signal": "BUY",
                "confidence": 0.72,
                "probability": 0.72,
                "expected_return": None,
                "risk_score": 0.3,
                "horizon": "5d",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "model_versions": {"xgboost": "1.0"},
            }

    class FakeKronosPath:
        def forecast(self, **kwargs):
            return {
                "net_forecast_change": 0.04,
                "forecast_change": 0.04,
                "historical": [{"close": 100.0}],
                "forecast": [
                    {"close": 102.0, "low": 99.0, "high": 103.0},
                    {"close": 104.0, "low": 100.5, "high": 105.0},
                ],
                "model": "ensemble",
                "engine": "ensemble",
            }

    provider = KronosForecastProvider(FakeKronosPath(), FakePrediction(), None)
    result = provider.get_forecast("NVDA")
    assert result.signal == "BUY"
    assert result.signal_source == "hybrid"
    assert result.model_name == "hybrid_prediction"
    assert result.expected_return == pytest.approx(0.04)
    assert result.path_expected_return == pytest.approx(0.04)
    assert result.path_target_price == pytest.approx(104.0)
    assert result.path_stop_price is not None and result.path_stop_price < 100.0


def test_provider_hold_when_hybrid_missing_even_if_path_bullish():
    from app.trading_agent.forecast_provider import KronosForecastProvider

    class FakeKronosPath:
        def forecast(self, **kwargs):
            return {
                "net_forecast_change": 0.08,
                "historical": [{"close": 50.0}],
                "forecast": [{"close": 54.0, "low": 49.0, "high": 55.0}],
            }

    provider = KronosForecastProvider(FakeKronosPath(), None, None)
    result = provider.get_forecast("AAPL")
    assert result.signal == "HOLD"
    assert result.signal_source == "unavailable"
    assert result.path_expected_return == pytest.approx(0.08)


def test_day_trading_uses_path_target_for_take_profit():
    strategy = DayTradingStrategy()
    risk = {
        "allow_day_trading": True,
        "max_position_size_pct": 0.1,
        "default_stop_loss_pct": 0.01,
        "default_take_profit_pct": 0.02,
    }
    forecast = ForecastResult(
        symbol="NVDA",
        signal="BUY",
        confidence=0.8,
        forecast_horizon="5d",
        expected_return=0.05,
        downside_risk=0.01,
        forecast_version="test",
        generated_at=datetime.now(timezone.utc).isoformat(),
        features_snapshot_id="snap",
        model_name="hybrid_prediction",
        signal_source="hybrid",
        path_expected_return=0.05,
        path_target_price=110.0,
        path_stop_price=97.0,
    )
    buys = strategy.generate("NVDA", forecast, 100.0, risk, 50_000)
    assert len(buys) == 1
    assert buys[0].take_profit == pytest.approx(110.0)
    assert buys[0].stop_loss == pytest.approx(97.0)


def test_day_trading_skips_when_signal_source_unavailable():
    strategy = DayTradingStrategy()
    risk = {"allow_day_trading": True, "max_position_size_pct": 0.1}
    forecast = ForecastResult(
        symbol="NVDA",
        signal="BUY",
        confidence=0.9,
        forecast_horizon="5d",
        expected_return=0.05,
        downside_risk=0.01,
        forecast_version="hybrid-unavailable",
        generated_at=datetime.now(timezone.utc).isoformat(),
        features_snapshot_id="snap",
        model_name="hybrid_unavailable",
        signal_source="unavailable",
        path_expected_return=0.08,
    )
    assert strategy.generate("NVDA", forecast, 100.0, risk, 50_000) == []


def test_day_trades_reports_same_day_win():
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        when = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
        _seed_filled_order(session, config=config, side="buy", quantity=5, price=100, filled_at=when)
        _seed_filled_order(
            session,
            config=config,
            side="sell",
            quantity=5,
            price=110,
            filled_at=when + timedelta(hours=1),
            strategy="intraday_exit",
        )
        session.commit()
        session.close()
        resp = client.get("/api/v1/trading-agent/day-trades?date=2026-09-10", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["date"] == "2026-09-10"
        sells = [row for row in data["trades"] if row["side"] == "sell"]
        assert len(sells) == 1
        assert sells[0]["result"] == "Profit"
        assert sells[0]["pnl"] == pytest.approx(50.0)
        assert data["summary"]["wins"] == 1
        assert data["summary"]["losses"] == 0
        assert data["summary"]["net_realized_pnl"] == pytest.approx(50.0)


def test_day_trades_reports_same_day_loss():
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        when = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
        _seed_filled_order(session, config=config, side="buy", quantity=5, price=100, filled_at=when)
        _seed_filled_order(
            session,
            config=config,
            side="sell",
            quantity=5,
            price=90,
            filled_at=when + timedelta(hours=1),
            strategy="intraday_exit",
        )
        session.commit()
        session.close()
        resp = client.get("/api/v1/trading-agent/day-trades?date=2026-09-10", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        sells = [row for row in data["trades"] if row["side"] == "sell"]
        assert len(sells) == 1
        assert sells[0]["result"] == "Loss"
        assert sells[0]["pnl"] == pytest.approx(-50.0)
        assert data["summary"]["losses"] == 1
        assert data["summary"]["net_realized_pnl"] == pytest.approx(-50.0)


def test_day_trades_empty_day():
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        when = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
        _seed_filled_order(session, config=config, side="buy", quantity=5, price=100, filled_at=when)
        session.commit()
        session.close()
        resp = client.get("/api/v1/trading-agent/day-trades?date=2026-09-11", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["date"] == "2026-09-11"
        assert data["trades"] == []
        assert data["summary"]["count"] == 0


def test_day_trades_open_buy_uses_mark():
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        when = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
        _seed_filled_order(session, config=config, side="buy", quantity=5, price=100, filled_at=when)
        session.add(
            AgentPosition(
                user_id=config.user_id,
                agent_config_id=config.id,
                symbol="NVDA",
                asset_type="equity",
                quantity=5,
                average_entry_price=100,
                current_price=105,
                unrealized_pnl=25,
            )
        )
        session.commit()
        session.close()
        resp = client.get("/api/v1/trading-agent/day-trades?date=2026-09-10", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        opens = [row for row in data["trades"] if row["status"] == "open"]
        assert len(opens) == 1
        assert opens[0]["result"] == "Open (profit)"
        assert opens[0]["pnl"] == pytest.approx(25.0)
        assert data["summary"]["open"] == 1
        assert data["summary"]["net_unrealized_pnl"] == pytest.approx(25.0)


def test_list_candidates_keeps_approved_buys_despite_reject_flood():
    """Accepted queue must not lose BUY approvals when recent rejects dominate."""
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        run = AgentRun(agent_config_id=config.id, status="completed", forecast_version="cand-window")
        session.add(run)
        session.flush()
        buy = TradeCandidate(
            agent_run_id=run.id,
            symbol="AAPL",
            asset_type="equity",
            strategy="buy_and_hold",
            forecast_snapshot={"signal": "BUY", "confidence": 0.8, "symbol": "AAPL"},
            status="approved",
        )
        session.add(buy)
        session.flush()
        for i in range(12):
            session.add(
                TradeCandidate(
                    agent_run_id=run.id,
                    symbol="MSFT",
                    asset_type="equity",
                    strategy="intraday_momentum",
                    forecast_snapshot={"signal": "HOLD", "confidence": 0.2, "symbol": "MSFT"},
                    risk_decision={"approved": False, "reason": f"reject-{i}"},
                    status="rejected",
                )
            )
        session.add(
            TradeCandidate(
                agent_run_id=run.id,
                symbol="AMZN",
                asset_type="equity",
                strategy="intraday_momentum",
                forecast_snapshot={"signal": "SELL", "confidence": 0.7, "symbol": "AMZN"},
                status="approved",
            )
        )
        session.commit()
        listed = agent.list_candidates(session, config, limit=5)
        approved = [row for row in listed if row["status"] == "approved"]
        rejected = [row for row in listed if row["status"] == "rejected"]
        assert any(row["symbol"] == "AAPL" and row["forecast_snapshot"]["signal"] == "BUY" for row in approved)
        assert any(row["symbol"] == "AMZN" and row["forecast_snapshot"]["signal"] == "SELL" for row in approved)
        assert len(rejected) == 5
        assert len(approved) == 2
        session.close()


def test_day_trades_defaults_to_latest_fill_session_day():
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        when = datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc)
        _seed_filled_order(session, config=config, side="buy", quantity=5, price=100, filled_at=when)
        _seed_filled_order(
            session,
            config=config,
            side="sell",
            quantity=5,
            price=110,
            filled_at=when + timedelta(hours=1),
            strategy="intraday_exit",
        )
        session.commit()
        session.close()
        resp = client.get("/api/v1/trading-agent/day-trades", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["date"] == "2026-09-16"
        assert data["latest_date"] == "2026-09-16"
        assert len(data["trades"]) >= 1
        empty = client.get("/api/v1/trading-agent/day-trades?date=2026-09-17", headers=headers)
        assert empty.status_code == 200, empty.text
        empty_data = empty.json()
        assert empty_data["date"] == "2026-09-17"
        assert empty_data["latest_date"] == "2026-09-16"
        assert empty_data["trades"] == []

    from app.trading_agent.broker import is_filled_status, normalize_order_status

    assert normalize_order_status("OrderStatus.FILLED") == "filled"
    assert normalize_order_status("OrderStatus.PARTIALLY_FILLED") == "partially_filled"
    assert normalize_order_status("accepted") == "accepted"
    assert is_filled_status("OrderStatus.FILLED")
    assert is_filled_status("partially_filled")
    assert not is_filled_status("OrderStatus.ACCEPTED")


def test_jsonable_prefers_str_enum_value_over_repr():
    from enum import Enum

    from app.services.providers import jsonable

    class OrderStatus(str, Enum):
        FILLED = "filled"
        ACCEPTED = "accepted"

    assert jsonable(OrderStatus.FILLED) == "filled"
    assert jsonable({"status": OrderStatus.ACCEPTED}) == {"status": "accepted"}


def test_day_trades_repairs_alpaca_enum_status_and_missing_filled_at():
    """Legacy rows stored as OrderStatus.FILLED with null filled_at must still report."""
    client, agent, _paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        when = datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc)
        buy = _seed_filled_order(session, config=config, side="buy", quantity=5, price=100, filled_at=when)
        sell = _seed_filled_order(
            session,
            config=config,
            side="sell",
            quantity=5,
            price=110,
            filled_at=when + timedelta(hours=1),
            strategy="intraday_exit",
        )
        buy.status = "OrderStatus.FILLED"
        buy.filled_at = None
        sell.status = "OrderStatus.FILLED"
        sell.filled_at = None
        session.commit()
        session.close()

        resp = client.get("/api/v1/trading-agent/day-trades?date=2026-09-16", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        sells = [row for row in data["trades"] if row["side"] == "sell"]
        assert len(sells) == 1
        assert sells[0]["result"] == "Profit"
        assert sells[0]["pnl"] == pytest.approx(50.0)

        orders = client.get("/api/v1/trading-agent/orders", headers=headers).json()["orders"]
        filled = [row for row in orders if row["status"] == "filled"]
        assert len(filled) >= 2
        assert all(row.get("filled_at") for row in filled)

        perf = client.get("/api/v1/trading-agent/performance", headers=headers).json()
        assert int(perf["number_of_trades"]) >= 2


def test_cycle_universe_scan_covers_every_symbol():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    agent.forecast_provider = StaticForecastProvider(
        {
            "NVDA": _forecast("BUY", expected_return=0.04),
            "MU": ForecastResult(
                symbol="MU",
                signal="HOLD",
                confidence=0.4,
                forecast_horizon="1Day",
                expected_return=0.0,
                downside_risk=0.01,
                forecast_version="test",
                generated_at=datetime.now(timezone.utc).isoformat(),
                features_snapshot_id="snap1",
                model_name="static",
            ),
        }
    )
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "long_term", "universe": ["NVDA", "MU"], "capital_allocation": 10_000},
            headers=headers,
        )
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        broker = paper_brokers[cfg["id"]]
        broker.set_price("NVDA", 100.0)
        broker.set_price("MU", 90.0)
        # Inflate paper equity so sizing is not stuck on the 10k allocation alone.
        broker.cash = 50_000.0
        cycle = client.post(
            "/api/v1/trading-agent/cycle",
            json={"symbols": ["NVDA", "MU"], "execute": True},
            headers=headers,
        )
        assert cycle.status_code == 200, cycle.text
        body = cycle.json()
        scan = {row["symbol"]: row for row in body["universe_scan"]}
        assert set(scan) == {"NVDA", "MU"}
        assert scan["NVDA"]["outcome"] in {"approved", "risk_rejected"}
        assert scan["MU"]["outcome"] == "hold"
        assert body["sizing_capital"] >= 10_000

        cfg_resp = client.get("/api/v1/trading-agent/config", headers=headers).json()
        assert cfg_resp["max_universe_size"] == 50
        assert len(cfg_resp["last_universe_scan"]) == 2
        assert {row["symbol"] for row in cfg_resp["last_universe_scan"]} == {"NVDA", "MU"}


def test_sizing_capital_prefers_broker_equity():
    client, agent, paper_brokers, _alpaca = make_agent_client()
    with client:
        headers = register_headers(client)
        cfg = client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers).json()
        broker = paper_brokers[cfg["id"]]
        broker.cash = 80_000.0
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        config.capital_allocation = 5_000
        session.commit()
        sized = agent._sizing_capital(config, broker)
        session.close()
        assert sized == pytest.approx(80_000.0)


def test_classify_empty_generate_qty_zero():
    from app.trading_agent.strategies import classify_empty_generate

    outcome, reason = classify_empty_generate(
        forecast=_forecast("BUY", expected_return=0.04),
        price=500.0,
        capital=1_000.0,
        risk_config={"max_position_size_pct": 0.05},
        held_qty=0.0,
    )
    assert outcome == "qty_zero"
    assert "budget" in reason.lower() or "0" in reason

