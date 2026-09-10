"""Model-agnostic forecast provider for the trading agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.trading_agent.risk_engine import ForecastResult


class ForecastProvider(Protocol):
    def get_forecast(self, symbol: str, timeframe: str) -> ForecastResult:
        ...


def _signal_from_change(change: float | None, confidence: float) -> str:
    if change is None:
        return "HOLD"
    if change > 0.02 and confidence >= 0.7:
        return "STRONG BUY"
    if change > 0.005:
        return "BUY"
    if change < -0.02 and confidence >= 0.7:
        return "STRONG SELL"
    if change < -0.005:
        return "SELL"
    return "HOLD"


class KronosForecastProvider:
    """Wraps existing KronosService / ensemble Forecast Mode — no second model."""

    def __init__(self, kronos_service: Any, prediction_service: Any | None = None) -> None:
        self.kronos = kronos_service
        self.prediction = prediction_service

    def get_forecast(self, symbol: str, timeframe: str = "1Day") -> ForecastResult:
        ticker = symbol.upper()
        # Prefer hybrid directional prediction when available
        if self.prediction is not None:
            try:
                payload = self.prediction.predict(ticker, horizon="5d")
                if isinstance(payload, dict) and payload.get("signal"):
                    conf = float(payload.get("confidence") or payload.get("probability") or 0.5)
                    expected = float(payload.get("expected_return") or 0.0)
                    downside = float(payload.get("risk_score") or 0.0) / 100.0
                    return ForecastResult(
                        symbol=ticker,
                        signal=str(payload.get("signal") or "HOLD").upper(),
                        confidence=conf,
                        forecast_horizon=str(payload.get("horizon") or timeframe),
                        expected_return=expected,
                        downside_risk=downside,
                        forecast_version=str(payload.get("model_version") or "hybrid-v1"),
                        generated_at=str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat()),
                        features_snapshot_id=str(payload.get("features_snapshot_id") or uuid4().hex),
                        model_name=str(payload.get("model") or "hybrid_prediction"),
                        raw=payload,
                    )
            except Exception:
                pass

        # Fall back to path forecast from existing Forecast Mode
        preset = "short" if timeframe in {"1Min", "5Min", "15Min", "1Hour"} else "long"
        path = self.kronos.forecast(
            symbol=ticker,
            preset=preset,
            timeframe=timeframe if timeframe in {"1Min", "5Min", "15Min", "1Hour", "1Day"} else "1Day",
            context=64,
            horizon=None,
            evaluate=False,
            engine="ensemble",
        )
        change = path.get("net_forecast_change")
        if change is None:
            change = path.get("forecast_change")
        try:
            change_f = float(change) if change is not None else 0.0
        except (TypeError, ValueError):
            change_f = 0.0
        confidence = 0.6 if path.get("edge_reliable") else 0.45
        signal = _signal_from_change(change_f, confidence)
        return ForecastResult(
            symbol=ticker,
            signal=signal,
            confidence=confidence,
            forecast_horizon=str(path.get("horizon") or preset),
            expected_return=change_f,
            downside_risk=abs(min(change_f, 0.0)),
            forecast_version=str(path.get("model") or "ensemble"),
            generated_at=str(path.get("generated_at") or datetime.now(timezone.utc).isoformat()),
            features_snapshot_id=uuid4().hex,
            model_name=str(path.get("engine") or path.get("model") or "forecast_mode"),
            raw=path,
        )


class StaticForecastProvider:
    """Test double / offline provider."""

    def __init__(self, results: dict[str, ForecastResult] | None = None) -> None:
        self.results = results or {}

    def get_forecast(self, symbol: str, timeframe: str = "1Day") -> ForecastResult:
        ticker = symbol.upper()
        if ticker in self.results:
            return self.results[ticker]
        return ForecastResult(
            symbol=ticker,
            signal="HOLD",
            confidence=0.5,
            forecast_horizon=timeframe,
            expected_return=0.0,
            downside_risk=0.0,
            forecast_version="static",
            generated_at=datetime.now(timezone.utc).isoformat(),
            features_snapshot_id="static",
            model_name="static",
        )
