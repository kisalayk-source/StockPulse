from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.config import Settings
from app.services.kronos import KronosService


class FakeAlpaca:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def bars(self, symbol, timeframe, start, end, limit):
        self.calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
            }
        )
        first = datetime(2026, 1, 2, tzinfo=timezone.utc)
        return [
            {
                "timestamp": (first + timedelta(days=index)).isoformat(),
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "volume": 1_000 + index,
            }
            for index in range(64)
        ]


class FakePredictor:
    device = "cpu"

    def predict(self, frame, x_timestamp, y_timestamp, pred_len, **kwargs):
        return pd.DataFrame(
            [
                {
                    "open": 164.0 + index,
                    "high": 165.0 + index,
                    "low": 163.0 + index,
                    "close": 164.5 + index,
                    "volume": 2_000 + index,
                    "amount": 329_000 + index,
                }
                for index in range(pred_len)
            ],
            index=y_timestamp,
        )


def test_long_forecast_requests_sufficient_history_and_caches_result() -> None:
    alpaca = FakeAlpaca()
    service = KronosService(Settings(_env_file=None), alpaca)
    service._predictor = FakePredictor()

    first = service.forecast("AAPL", "long")
    second = service.forecast("AAPL", "long")

    assert first == second
    assert len(alpaca.calls) == 1
    request = alpaca.calls[0]
    assert request["timeframe"] == "1Day"
    assert request["limit"] == 256
    assert request["end"] - request["start"] >= timedelta(days=512)
    assert len(first["forecast"]) == 20
    assert first["model"]["context"] == 64
    assert first["costs"]["round_trip_bps"] > 0
    assert first["trend"]["net_forecast_change"] <= first["trend"]["forecast_change"]
    assert first["regime"]["label"]
    assert first["evaluation"]["folds"] >= 2
    assert first["evaluation"]["fill"] == "next_open"


def test_forecast_journal_can_persist_across_service_restarts(tmp_path) -> None:
    journal = tmp_path / "forecast-journal.jsonl"
    config = Settings(_env_file=None, kronos_journal_path=str(journal))
    service = KronosService(config, FakeAlpaca())
    service._predictor = FakePredictor()

    service.forecast("AAPL", "short", evaluate=False)

    assert journal.exists()
    restarted = KronosService(config, FakeAlpaca())
    assert len(restarted._journal) == 1
    assert restarted._journal[0]["symbol"] == "AAPL"


def test_intraday_prediction_rolls_from_market_close_to_next_session() -> None:
    timestamps = KronosService._future_timestamps(
        datetime(2026, 8, 12, 19, 55, tzinfo=timezone.utc),
        "5Min",
        2,
    )

    assert timestamps[0].isoformat() == "2026-08-13T09:30:00-04:00"
    assert timestamps[1].isoformat() == "2026-08-13T09:35:00-04:00"


def test_scan_movers_ranks_by_predicted_move_and_reuses_cache() -> None:
    alpaca = FakeAlpaca()
    alpaca.universe_calls = 0

    def most_actives(top=60):
        alpaca.universe_calls += 1
        return [{"symbol": "NVDA"}, {"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "F"}]

    alpaca.market_clock = lambda mode="paper": {
        "is_open": True,
        "session": "regular",
        "timestamp": "2026-08-12T18:00:00+00:00",
    }
    alpaca.most_actives = most_actives
    alpaca.movers = lambda top=20: {"gainers": [], "losers": []}
    alpaca.snapshots_many = lambda symbols: {
        symbol: {
            "current_price": 101.0,
            "daily": {"close": 101.0, "volume": 1_000_000},
            "previous_daily": {"close": 100.0},
        }
        for symbol in symbols
    }
    alpaca.bars_many = lambda symbols, timeframe, start, end, limit: {
        symbol: alpaca.bars(symbol, timeframe, start, end, limit) for symbol in symbols
    }

    changes = {"NVDA": 0.15, "AAPL": -0.09, "MSFT": 0.01, "F": 0.04}
    service = KronosService(Settings(_env_file=None), alpaca)

    def fake_forecast(symbol, preset, timeframe=None, context=None, horizon=None, bars=None, use_cache=True, evaluate=True):
        change = changes[symbol]
        return {
            "symbol": symbol,
            "as_of": "2026-08-12T18:00:00+00:00",
            "trend": {
                "direction": "up" if change > 0 else "down",
                "forecast_change": change,
            },
            "historical": [{"close": 100.0}],
            "forecast": [{"close": 100.0 * (1 + change)}],
        }

    service.forecast = fake_forecast  # type: ignore[method-assign]

    first = service.scan_movers(limit=3)
    second = service.scan_movers(limit=3)

    assert [item["symbol"] for item in first["movers"]] == ["NVDA", "AAPL", "F"]
    assert first["movers"][0]["forecast_change"] == 0.15
    assert first["movers"][1]["day_change"] == pytest.approx(0.01)
    assert first["cached"] is False
    assert second["cached"] is True
    assert alpaca.universe_calls == 1

    refreshed = service.scan_movers(limit=3, refresh=True)
    assert refreshed["cached"] is False
    assert alpaca.universe_calls == 2

    service._scan_cache.clear()
    started = service.start_movers_scan(limit=3)
    assert started["status"] == "pending"
    assert service._scan_thread is not None
    service._scan_thread.join(timeout=5)
    progress = service.movers_scan_status()
    assert progress["status"] == "ready"
    assert [item["symbol"] for item in progress["gainers"]] == ["NVDA", "F", "MSFT"]
    assert [item["symbol"] for item in progress["losers"]] == ["AAPL"]
