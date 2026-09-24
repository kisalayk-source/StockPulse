"""OCC selection and option order submit."""

from __future__ import annotations

from datetime import date

from app.trading_agent.broker import AlpacaBrokerAdapter, OrderRequest
from app.trading_agent.option_orders import select_bull_call_spread, select_single_contract


def _contract(symbol: str, expiration: str, strike: float, right: str, tradable: bool = True) -> dict:
    return {
        "symbol": symbol,
        "expiration_date": expiration,
        "strike_price": strike,
        "type": right,
        "tradable": tradable,
    }


def test_selects_nearest_expiration_and_strike():
    today = date(2026, 9, 23)
    contracts = [
        _contract("AR260925C00020000", "2026-09-25", 20, "call"),
        _contract("AR261016C00021000", "2026-10-16", 21, "call"),
        _contract("AR261016C00025000", "2026-10-16", 25, "call"),
        _contract("AR261016C00018000", "2026-10-16", 18, "call"),
        _contract("AR261016P00018000", "2026-10-16", 18, "put"),
        _contract("AR261016C00022000", "2026-10-16", 22, "call", tradable=False),
    ]
    chosen = select_single_contract(
        contracts,
        right="call",
        target_strike=20.5,
        target_dte=30,
        today=today,
        min_dte=7,
        max_dte=60,
    )
    assert chosen is not None
    assert chosen["symbol"] == "AR261016C00021000"
    assert chosen["days_to_expiration"] == 23

    spread = select_bull_call_spread(
        contracts,
        long_strike=20,
        short_strike=22,
        target_dte=35,
        today=today,
        min_dte=7,
        max_dte=60,
    )
    assert spread is not None
    long_leg, short_leg = spread
    assert long_leg["symbol"] == "AR261016C00021000"
    assert short_leg["symbol"] == "AR261016C00025000"
    assert short_leg["strike"] > long_leg["strike"]


def test_fit_option_contracts_uses_real_premium():
    from app.trading_agent.option_orders import fit_option_contracts

    risk = {"max_premium_per_trade": 500, "max_loss_per_options_position": 250, "max_order_quantity": 10}
    assert fit_option_contracts(10, 1.0, risk) == 2
    assert fit_option_contracts(10, 0.20, risk) == 10
    assert fit_option_contracts(1, 6.0, risk) is None


def test_bear_put_short_strike_is_below_long_strike():
    from app.trading_agent.option_orders import select_bear_put_spread

    today = date(2026, 9, 23)
    contracts = [
        _contract("AR261016P00020000", "2026-10-16", 20, "put"),
        _contract("AR261016P00018000", "2026-10-16", 18, "put"),
        _contract("AR261016P00022000", "2026-10-16", 22, "put"),
    ]
    spread = select_bear_put_spread(
        contracts,
        long_strike=20,
        short_strike=18,
        target_dte=30,
        today=today,
        min_dte=7,
        max_dte=60,
    )
    assert spread is not None
    long_leg, short_leg = spread
    assert long_leg["strike"] == 20
    assert short_leg["strike"] == 18
    assert short_leg["strike"] < long_leg["strike"]


class _RecordingAlpaca:
    def __init__(self) -> None:
        self.spread_orders: list[object] = []
        self.contract_lookups: list[str] = []

    def submit_option_spread(self, order: object) -> dict:
        self.spread_orders.append(order)
        return {"id": "spread-1", "status": "accepted"}

    def submit_option_order(self, order: object) -> dict:
        raise AssertionError("single-leg submit should not run")

    def get_option_contract(self, symbol: str) -> object:
        self.contract_lookups.append(symbol)
        raise AssertionError("ticker must not be looked up")


def test_bull_call_spread_submits_two_occ_legs():
    alpaca = _RecordingAlpaca()
    adapter = AlpacaBrokerAdapter(alpaca, mode="paper")
    result = adapter.submit_order(
        OrderRequest(
            symbol="AR",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=1.25,
            asset_type="option",
            mode="paper",
            legs=[
                {"symbol": "AR261016C00050000", "side": "buy", "position_intent": "buy_to_open", "ratio_qty": 1},
                {"symbol": "AR261016C00055000", "side": "sell", "position_intent": "sell_to_open", "ratio_qty": 1},
            ],
        )
    )
    assert result.status == "accepted"
    assert alpaca.contract_lookups == []
    order = alpaca.spread_orders[0]
    symbols = [leg["symbol"] for leg in order.legs]
    assert symbols == ["AR261016C00050000", "AR261016C00055000"]
    assert order.limit_price == 1.25
    assert "AR" not in symbols


def test_stock_ticker_option_order_is_rejected_locally():
    alpaca = _RecordingAlpaca()
    adapter = AlpacaBrokerAdapter(alpaca, mode="paper")
    result = adapter.submit_order(
        OrderRequest(
            symbol="AR",
            side="buy",
            quantity=1,
            asset_type="option",
            contract_symbol="AR",
            mode="paper",
        )
    )
    assert result.status == "rejected"
    assert "AR" in (result.error_message or "")
    assert alpaca.contract_lookups == []
    assert alpaca.spread_orders == []


def test_chain_miss_rejects_candidate_before_accept():
    from test_trading_agent import _db_session, make_agent_client, register_headers

    class EmptyChain:
        def __init__(self) -> None:
            self.submitted: list[object] = []

        def account(self, mode: str) -> dict:
            return {"equity": 100000, "cash": 100000, "buying_power": 100000}

        def positions(self, mode: str) -> list:
            return []

        def orders(self, mode: str, status: str, limit: int) -> list:
            return []

        def snapshot(self, symbol: str) -> dict:
            return {"symbol": symbol.upper(), "current_price": 30.0}

        def option_contracts(self, *args, **kwargs) -> list:
            return []

        def submit_option_order(self, order: object) -> dict:
            self.submitted.append(order)
            return {"id": "nope", "status": "accepted"}

        def submit_option_spread(self, order: object) -> dict:
            self.submitted.append(order)
            return {"id": "nope", "status": "accepted"}

    client, agent, _paper, _alpaca = make_agent_client()
    chain = EmptyChain()
    with client:
        headers = register_headers(client)
        client.put(
            "/api/v1/trading-agent/config",
            json={"trading_type": "options", "universe": ["NVDA"], "capital_allocation": 10000},
            headers=headers,
        )
        client.post("/api/v1/trading-agent/start", json={"mode": "paper"}, headers=headers)
        session = _db_session()
        me = client.get("/api/v1/auth/me", headers=headers).json()
        config = agent.get_or_create_config(session, me["id"])
        agent.alpaca = chain
        result = agent.run_cycle(session, config, symbols=["NVDA"], execute=True, market_open=True)
        session.close()
        assert result["approved"] == []
        assert result["rejected"]
        assert all(
            "contract" in row["reason"].lower() or "tradable" in row["reason"].lower()
            for row in result["rejected"]
        )
        assert chain.submitted == []
