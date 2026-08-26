from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.config import Settings
from app.services.kronos import (
    KronosService,
    MIN_SCAN_VOLUME_IEX,
    MIN_SCAN_VOLUME_SIP,
)


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

    def __init__(self) -> None:
        self.last_kwargs: dict = {}

    def predict(self, frame, x_timestamp, y_timestamp, pred_len, **kwargs):
        self.last_kwargs = dict(kwargs)
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


def test_predict_passes_smoother_sampling_settings() -> None:
    alpaca = FakeAlpaca()
    settings = Settings(
        _env_file=None,
        kronos_temperature=0.6,
        kronos_sample_count=5,
        kronos_top_p=0.9,
        kronos_eval_folds=0,
    )
    service = KronosService(settings, alpaca)
    predictor = FakePredictor()
    service._predictor = predictor

    result = service.forecast("AAPL", "long")

    assert predictor.last_kwargs["sample_count"] == 5
    assert predictor.last_kwargs["T"] == 0.6
    assert predictor.last_kwargs["top_p"] == 0.9
    assert result["model"]["sample_count"] == 5
    assert result["model"]["temperature"] == 0.6
    assert result["model"]["top_p"] == 0.9


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
    assert first["path_segments"]
    assert first["path_segments"][0]["direction"] in {"up", "down", "flat"}
    assert first["model"]["engine"] == "kronos"


def test_ensemble_forecast_uses_separate_cache_and_skips_oos_eval() -> None:
    alpaca = FakeAlpaca()
    service = KronosService(Settings(_env_file=None, kronos_eval_folds=3), alpaca)
    service._predictor = FakePredictor()

    def fake_ensemble(symbol, bars, timeframe, horizon, context):
        predicted = pd.DataFrame(
            {
                "open": [200.0 + i for i in range(horizon)],
                "high": [201.0 + i for i in range(horizon)],
                "low": [199.0 + i for i in range(horizon)],
                "close": [200.5 + i for i in range(horizon)],
                "volume": [0.0] * horizon,
                "amount": [0.0] * horizon,
            }
        )
        meta = {
            "id": "ensemble",
            "tokenizer_id": "none",
            "device": "cpu",
            "context": context,
            "horizon": horizon,
            "fallback": False,
            "engine": "ensemble",
            "strategy": "weighted_average",
            "models_used": ["persistence", "kronos"],
            "weights": {"persistence": 0.5, "kronos": 1.0},
        }
        return predicted, meta

    service._ensemble_predict_frame = fake_ensemble  # type: ignore[method-assign]

    kronos = service.forecast("AAPL", "short", horizon=5, evaluate=False, engine="kronos")
    ensemble = service.forecast("AAPL", "short", horizon=5, engine="ensemble")
    ensemble_cached = service.forecast("AAPL", "short", horizon=5, engine="ensemble")

    assert kronos["model"]["engine"] == "kronos"
    assert ensemble["model"]["engine"] == "ensemble"
    assert ensemble["model"]["id"] == "ensemble"
    assert ensemble["model"]["models_used"] == ["persistence", "kronos"]
    assert len(ensemble["forecast"]) == 5
    assert ensemble["evaluation"]["folds"] == 0
    assert ensemble is ensemble_cached
    assert kronos is not ensemble
    assert len(alpaca.calls) == 2


def test_ensemble_is_persistence_only_helper() -> None:
    assert KronosService._ensemble_is_persistence_only(["persistence"]) is True
    assert KronosService._ensemble_is_persistence_only(["persistence", "kronos"]) is False
    assert KronosService._ensemble_is_persistence_only(["kronos"]) is False
    assert KronosService._ensemble_is_persistence_only([]) is False


def test_ensemble_persistence_only_falls_back_to_predict_frame(monkeypatch) -> None:
    import importlib
    import sys
    from pathlib import Path

    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)

    from forecasting.core.schema import ForecastResult

    combine_mod = importlib.import_module("forecasting.ensemble.combine")

    alpaca = FakeAlpaca()
    service = KronosService(Settings(_env_file=None), alpaca)
    service._predictor = FakePredictor()

    def persistence_only(models, inp, **kwargs):
        last = float(inp.ohlcv["close"].iloc[-1])
        flat = pd.DataFrame({"close": [last] * inp.horizon})
        member = ForecastResult(model_name="persistence", ticker=inp.ticker, predicted=flat)
        blended = ForecastResult(model_name="ensemble", ticker=inp.ticker, predicted=flat.copy())
        return [member], blended

    monkeypatch.setattr(combine_mod, "forecast_ensemble", persistence_only)

    bars = alpaca.bars("AAPL", "1Day", datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 3, 1, tzinfo=timezone.utc), 64)
    predicted, meta = service._ensemble_predict_frame("AAPL", bars, "1Day", 5, 64)

    assert meta["ensemble_degraded"] is True
    assert meta["fallback_from"] == "ensemble"
    assert meta["engine"] == "ensemble"
    assert meta["models_used"] == ["persistence"]
    closes = [float(v) for v in predicted["close"].tolist()]
    assert len(closes) == 5
    # FakePredictor path is not a flat last-close line
    assert len({round(c, 6) for c in closes}) > 1


def test_baseline_forecast_when_predictor_unavailable() -> None:
    alpaca = FakeAlpaca()
    service = KronosService(Settings(_env_file=None), alpaca)
    service._predictor_load_error = "torch blocked for test"

    result = service.forecast("AAPL", "short", horizon=5, evaluate=False)

    assert len(result["forecast"]) == 5
    assert result["model"]["id"] == "baseline-drift"
    assert result["model"]["fallback"] is True
    assert result["trend"]["forecast_change"] is not None

    alpaca = FakeAlpaca()
    service = KronosService(Settings(_env_file=None), alpaca)
    service._predictor = FakePredictor()

    short_ten = service.forecast("AAPL", "short", horizon=10, evaluate=False)
    short_thirty = service.forecast("AAPL", "short", horizon=30, evaluate=False)

    assert len(short_ten["forecast"]) == 10
    assert len(short_thirty["forecast"]) == 30
    assert short_ten["model"]["horizon"] == 10
    assert short_thirty["model"]["horizon"] == 30
    assert len(alpaca.calls) == 2


def test_path_segments_split_on_direction_turns() -> None:
    from app.services.kronos import path_segments

    closes = [100.0, 101.0, 102.5, 101.0, 99.5]
    segments = path_segments(closes, ["t0", "t1", "t2", "t3", "t4"])

    assert len(segments) >= 2
    assert segments[0]["direction"] == "up"
    assert segments[-1]["direction"] == "down"
    assert segments[0]["start_timestamp"] == "t0"


def test_forecast_caps_oos_eval_horizon_for_long_paths() -> None:
    alpaca = FakeAlpaca()
    service = KronosService(Settings(_env_file=None, kronos_eval_folds=2, kronos_eval_context=32), alpaca)
    service._predictor = FakePredictor()
    seen: list[int] = []

    def track(window, timeframe, horizon):
        seen.append(horizon)
        return 0.01

    service._predict_change = track  # type: ignore[method-assign]
    result = service.forecast("AAPL", "long", horizon=60)

    assert result["model"]["horizon"] == 60
    assert result["evaluation"]["eval_horizon"] == 20
    assert seen
    assert all(horizon == 20 for horizon in seen)

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


def test_scan_universe_is_blue_chip_only() -> None:
    service = KronosService(Settings(_env_file=None), FakeAlpaca())
    symbols = service._scan_universe()
    assert "AAPL" in symbols
    assert "NVDA" in symbols
    assert "F" not in symbols
    assert "SPY" not in symbols
    assert "COIN" not in symbols
    assert "ARKK" not in symbols
    assert len(symbols) == len(set(symbols))


def test_scan_movers_ranks_by_predicted_move_and_reuses_cache() -> None:
    alpaca = FakeAlpaca()
    alpaca.snapshot_calls = 0

    alpaca.market_clock = lambda mode="paper": {
        "is_open": True,
        "session": "regular",
        "timestamp": "2026-08-12T18:00:00+00:00",
    }

    def snapshots_many(symbols):
        alpaca.snapshot_calls += 1
        return {
            symbol: {
                "current_price": 101.0,
                "daily": {"close": 101.0, "volume": 10_000_000},
                "previous_daily": {"close": 100.0},
            }
            for symbol in symbols
        }

    alpaca.snapshots_many = snapshots_many
    alpaca.bars_many = lambda symbols, timeframe, start, end, limit: {
        symbol: alpaca.bars(symbol, timeframe, start, end, limit) for symbol in symbols
    }

    changes = {"NVDA": 0.15, "AAPL": -0.09, "MSFT": 0.01, "JPM": 0.04}
    service = KronosService(Settings(_env_file=None), alpaca)
    service._scan_universe = lambda: ["NVDA", "AAPL", "MSFT", "JPM"]  # type: ignore[method-assign]

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
            "forecast": [{"close": 100.0 * (1 + change), "timestamp": "2026-08-12T19:00:00+00:00"}],
        }

    service.forecast = fake_forecast  # type: ignore[method-assign]

    first = service.scan_movers(limit=3)
    second = service.scan_movers(limit=3)

    assert [item["symbol"] for item in first["movers"]] == ["NVDA", "AAPL", "JPM"]
    assert first["movers"][0]["forecast_change"] == 0.15
    assert first["movers"][1]["day_change"] == pytest.approx(0.01)
    assert first["cached"] is False
    assert second["cached"] is True
    assert alpaca.snapshot_calls == 1

    refreshed = service.scan_movers(limit=3, refresh=True)
    assert refreshed["cached"] is False
    assert alpaca.snapshot_calls == 2

    service._scan_cache.clear()
    started = service.start_movers_scan(limit=3)
    assert started["status"] == "pending"
    assert service._scan_thread is not None
    service._scan_thread.join(timeout=5)
    progress = service.movers_scan_status()
    assert progress["status"] == "ready"
    assert [item["symbol"] for item in progress["gainers"]] == ["NVDA", "JPM", "MSFT"]
    assert [item["symbol"] for item in progress["losers"]] == ["AAPL"]


def test_scan_movers_skips_thin_volume_blue_chips() -> None:
    alpaca = FakeAlpaca()
    alpaca.market_clock = lambda mode="paper": {
        "is_open": True,
        "session": "regular",
        "timestamp": "2026-08-12T18:00:00+00:00",
    }
    alpaca.snapshots_many = lambda symbols: {
        "AAPL": {
            "current_price": 101.0,
            "daily": {"close": 101.0, "volume": 10_000_000},
            "previous_daily": {"close": 100.0, "volume": 12_000_000},
        },
        "MSFT": {
            "current_price": 101.0,
            # Thin on both sessions → skip under the IEX floor
            "daily": {"close": 101.0, "volume": 80_000},
            "previous_daily": {"close": 100.0, "volume": 90_000},
        },
    }
    alpaca.bars_many = lambda symbols, timeframe, start, end, limit: {
        symbol: alpaca.bars(symbol, timeframe, start, end, limit) for symbol in symbols
    }

    service = KronosService(Settings(_env_file=None), alpaca)
    service._scan_universe = lambda: ["AAPL", "MSFT"]  # type: ignore[method-assign]
    forecasted: list[str] = []

    def fake_forecast(symbol, preset, timeframe=None, context=None, horizon=None, bars=None, use_cache=True, evaluate=True):
        forecasted.append(symbol)
        return {
            "symbol": symbol,
            "as_of": "2026-08-12T18:00:00+00:00",
            "trend": {"direction": "up", "forecast_change": 0.05},
            "historical": [{"close": 100.0}],
            "forecast": [{"close": 105.0, "timestamp": "2026-08-12T19:00:00+00:00"}],
        }

    service.forecast = fake_forecast  # type: ignore[method-assign]
    result = service.scan_movers(limit=5)

    assert forecasted == ["AAPL"]
    assert [item["symbol"] for item in result["movers"]] == ["AAPL"]
    assert any(item["symbol"] == "MSFT" for item in result["skipped"])
    assert "volume" in next(item["message"] for item in result["skipped"] if item["symbol"] == "MSFT").lower()


def test_min_scan_volume_depends_on_data_feed() -> None:
    iex = KronosService(Settings(_env_file=None, alpaca_data_feed="iex"), FakeAlpaca())
    sip = KronosService(Settings(_env_file=None, alpaca_data_feed="sip"), FakeAlpaca())
    assert iex._min_scan_volume() == MIN_SCAN_VOLUME_IEX
    assert sip._min_scan_volume() == MIN_SCAN_VOLUME_SIP


def test_snapshot_volume_uses_prior_day_when_session_is_partial() -> None:
    snapshot = {
        "daily": {"volume": 400_000},
        "previous_daily": {"volume": 55_000_000},
    }
    assert KronosService._snapshot_volume(snapshot) == 55_000_000
