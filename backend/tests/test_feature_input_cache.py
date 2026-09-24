"""Cached SEC, fundamentals, and government inputs for prediction and the agent scan."""

from __future__ import annotations

from app.config import Settings
from app.services.prediction import PredictionService
from app.trading_agent.forecast_provider import KronosForecastProvider


def _settings() -> Settings:
    return Settings(_env_file=None, app_environment="test", prediction_enabled=False, api_key=None)


class _Sec:
    def __init__(self) -> None:
        self.calls = 0

    def load_normalized_events(self, session, ticker: str) -> list:
        self.calls += 1
        return []


class _Government:
    def __init__(self) -> None:
        self.calls = 0

    def events_as_dicts(self, session, ticker: str) -> list:
        self.calls += 1
        return []

    config: dict = {}


class _Finnhub:
    def __init__(self) -> None:
        self.calls = 0

    async def extended_fundamentals(self, symbol: str) -> dict:
        self.calls += 1
        return {}


def test_empty_feature_inputs_are_not_refetched() -> None:
    sec = _Sec()
    government = _Government()
    finnhub = _Finnhub()
    service = PredictionService(_settings(), alpaca=None, finnhub=finnhub, sec=sec, government=government)
    first = service.cached_feature_inputs(object(), "ZZZZ")
    second = service.cached_feature_inputs(object(), "ZZZZ")
    assert first["sec_events"] == []
    assert first["fundamentals_metrics"] == {}
    assert first["government_events"] == []
    assert second == first
    assert sec.calls == 1
    assert government.calls == 1
    assert finnhub.calls == 1


def test_disabled_feature_flag_is_not_loaded() -> None:
    sec = _Sec()
    government = _Government()
    finnhub = _Finnhub()
    service = PredictionService(_settings(), alpaca=None, finnhub=finnhub, sec=sec, government=government)
    service.engine.config["features"] = {"sec": False, "fundamentals": False, "government": True}
    loaded = service.cached_feature_inputs(object(), "ZZZZ")
    assert "sec_events" not in loaded
    assert "fundamentals_metrics" not in loaded
    assert loaded["government_events"] == []
    assert sec.calls == 0
    assert finnhub.calls == 0
    assert government.calls == 1


def test_scan_forecast_passes_cached_feature_inputs() -> None:
    class _Prediction:
        def cached_feature_inputs(self, session, ticker: str) -> dict:
            return {
                "sec_events": [],
                "fundamentals_metrics": {},
                "government_events": [{"event_id": "award"}],
            }

        def predict(self, ticker: str, **kwargs):
            self.kwargs = kwargs
            return {
                "signal": "HOLD",
                "confidence": 0.4,
                "probability": 0.4,
                "horizon": kwargs.get("horizon"),
                "timestamp": "2026-09-23T00:00:00+00:00",
                "model_versions": {},
            }

    prediction = _Prediction()
    provider = KronosForecastProvider(None, prediction, None)
    result = provider.get_forecast("AR", trading_type="mixed", session=object())
    assert result.signal == "HOLD"
    assert prediction.kwargs["sec_events"] == []
    assert prediction.kwargs["fundamentals_metrics"] == {}
    assert prediction.kwargs["government_events"] == [{"event_id": "award"}]
    assert prediction.kwargs["horizon"] == "5d"
