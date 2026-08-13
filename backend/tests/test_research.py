from types import SimpleNamespace

import pytest

from app.config import Settings
from app.schemas import EquityOrderRequest
from app.services.research import (
    classify_regime,
    edge_is_reliable,
    net_expected_change,
    round_trip_cost,
    walk_forward_evaluate,
)
from app.services.risk import check_order_risk


def _bars(count: int = 80, start: float = 100.0) -> list[dict]:
    return [
        {
            "timestamp": f"2026-01-{index + 1:02d}T00:00:00+00:00" if index < 31 else f"2026-02-{index - 30:02d}T00:00:00+00:00",
            "open": start + index,
            "high": start + index + 1.5,
            "low": start + index - 0.5,
            "close": start + index + 0.4,
            "volume": 2_000_000,
        }
        for index in range(count)
    ]


def test_round_trip_cost_scales_with_range_and_stays_bounded() -> None:
    costs = round_trip_cost(_bars())
    assert 2 <= costs["spread_bps"] <= 80
    assert costs["round_trip_bps"] >= costs["spread_bps"] * 2


def test_net_expected_change_applies_haircut_to_both_sides() -> None:
    assert net_expected_change(0.02, 20) == pytest.approx(0.018)
    assert net_expected_change(-0.02, 20) == pytest.approx(-0.018)


def test_classify_regime_detects_uptrend() -> None:
    regime = classify_regime(_bars())
    assert regime["trend"] == "up"
    assert regime["label"].endswith("_up")


def test_walk_forward_uses_next_open_fill_and_costs() -> None:
    bars = _bars(70)

    def predict(_window: list[dict]) -> float:
        return 0.03

    result = walk_forward_evaluate(bars, predict, horizon=5, context=20, max_folds=4, stride=5)
    assert result["folds"] == 4
    assert result["fill"] == "next_open"
    assert result["hit_rate"] == 1.0
    assert result["mean_net_return"] is not None
    assert result["mean_net_return"] < result["mean_gross_return"]


def test_edge_requires_positive_net_and_enough_folds() -> None:
    assert not edge_is_reliable({"folds": 1, "mean_net_return": 0.02, "hit_rate": 1})
    assert not edge_is_reliable({"folds": 4, "mean_net_return": -0.01, "hit_rate": 0.8})
    assert edge_is_reliable({"folds": 4, "mean_net_return": 0.01, "hit_rate": 0.6})


def test_check_order_risk_blocks_daily_loss_and_position_size() -> None:
    settings = Settings(_env_file=None)
    account = SimpleNamespace(equity=10_000, last_equity=10_000, buying_power=50_000)
    snapshot = {"symbol": "AAPL", "current_price": 200, "daily": {"volume": 5_000_000, "high": 201, "low": 199, "close": 200}}
    order = EquityOrderRequest(mode="paper", symbol="AAPL", side="buy", notional=2_000)
    with pytest.raises(ValueError, match="position"):
        check_order_risk(order, account=account, positions=[], snapshot=snapshot, settings=settings)

    halted = SimpleNamespace(equity=9_600, last_equity=10_000, buying_power=50_000)
    small = EquityOrderRequest(mode="paper", symbol="AAPL", side="buy", notional=100)
    with pytest.raises(ValueError, match="New buys halted"):
        check_order_risk(small, account=halted, positions=[], snapshot=snapshot, settings=settings)

    ok = check_order_risk(
        EquityOrderRequest(mode="paper", symbol="AAPL", side="buy", notional=400),
        account=account,
        positions=[],
        snapshot=snapshot,
        settings=settings,
    )
    assert ok["ok"] is True
    assert ok["estimated_cost"] == 400
