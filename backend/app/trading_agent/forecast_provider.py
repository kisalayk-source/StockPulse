"""Model-agnostic forecast provider for the trading agent.

Agent alignment: calibrated hybrid prediction owns BUY/HOLD/SELL. Kronos (or
ensemble) path forecasts supply expected move / target / stop hints for sizing
only — never a rival directional signal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.trading_agent.risk_engine import ForecastResult


class ForecastProvider(Protocol):
    def get_forecast(self, symbol: str, timeframe: str) -> ForecastResult:
        ...


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_path_metrics(path: dict[str, Any], *, spot: float | None = None) -> dict[str, float | None]:
    """Pull sizing/target fields from a Kronos/ensemble path payload."""
    change = path.get("net_forecast_change")
    if change is None:
        change = path.get("forecast_change")
    if change is None:
        change = (path.get("trend") or {}).get("net_forecast_change") or (path.get("trend") or {}).get(
            "forecast_change"
        )
    change_f = _as_float(change, 0.0)

    forecast_rows = path.get("forecast") or []
    target_price: float | None = None
    path_low: float | None = None
    path_high: float | None = None
    if isinstance(forecast_rows, list) and forecast_rows:
        closes = [_as_float(row.get("close"), float("nan")) for row in forecast_rows if isinstance(row, dict)]
        lows = [_as_float(row.get("low"), float("nan")) for row in forecast_rows if isinstance(row, dict)]
        highs = [_as_float(row.get("high"), float("nan")) for row in forecast_rows if isinstance(row, dict)]
        finite_closes = [c for c in closes if c == c]
        finite_lows = [v for v in lows if v == v]
        finite_highs = [v for v in highs if v == v]
        if finite_closes:
            target_price = float(finite_closes[-1])
        if finite_lows:
            path_low = float(min(finite_lows))
        if finite_highs:
            path_high = float(max(finite_highs))

    stop_price: float | None = None
    if spot is not None and spot > 0:
        if change_f >= 0:
            # Long-biased path: stop near path low or a fraction of the expected move.
            if path_low is not None and path_low < spot:
                stop_price = path_low
            else:
                stop_price = spot * (1.0 - max(0.005, abs(change_f) * 0.5))
        else:
            if path_high is not None and path_high > spot:
                stop_price = path_high
            else:
                stop_price = spot * (1.0 + max(0.005, abs(change_f) * 0.5))
        if target_price is None:
            target_price = spot * (1.0 + change_f)

    return {
        "expected_return": change_f,
        "downside_risk": abs(min(change_f, 0.0)),
        "target_price": target_price,
        "stop_price": stop_price,
        "path_low": path_low,
        "path_high": path_high,
    }


class KronosForecastProvider:
    """Hybrid signal + Kronos path sizing — path never invents BUY/SELL."""

    def __init__(
        self,
        kronos_service: Any,
        prediction_service: Any | None = None,
        alpaca: Any | None = None,
        *,
        require_hybrid_signal: bool = True,
    ) -> None:
        self.kronos = kronos_service
        self.prediction = prediction_service
        self.alpaca = alpaca
        self.require_hybrid_signal = bool(require_hybrid_signal)

    def get_forecast(self, symbol: str, timeframe: str = "1Day") -> ForecastResult:
        ticker = symbol.upper()
        now = datetime.now(timezone.utc).isoformat()
        hybrid = self._hybrid_payload(ticker)
        path_payload, path_error = self._path_payload(ticker, timeframe)
        spot = self._spot_price(ticker, path_payload)
        path_metrics = _extract_path_metrics(path_payload or {}, spot=spot) if path_payload else {}

        if hybrid is not None:
            signal = str(hybrid.get("signal") or "HOLD").upper()
            conf = _as_float(hybrid.get("confidence"), _as_float(hybrid.get("probability"), 0.5))
            # Path owns expected move for risk gates / sizing; hybrid risk_score is not a return.
            path_ret = path_metrics.get("expected_return")
            expected = float(path_ret) if path_ret is not None else _as_float(hybrid.get("expected_return"), 0.0)
            downside = float(path_metrics.get("downside_risk") or 0.0)
            if downside <= 0:
                downside = _as_float(hybrid.get("risk_score"), 0.0) * 0.01
            versions = hybrid.get("model_versions") or {}
            version = (
                str(hybrid.get("model_version") or "")
                or ",".join(f"{k}:{v}" for k, v in versions.items())
                or "hybrid-v1"
            )
            return ForecastResult(
                symbol=ticker,
                signal=signal,
                confidence=conf,
                forecast_horizon=str(hybrid.get("horizon") or timeframe),
                expected_return=expected,
                downside_risk=downside,
                forecast_version=version,
                generated_at=str(hybrid.get("timestamp") or now),
                features_snapshot_id=str(
                    (hybrid.get("feature_snapshot") or {}).get("snapshot_id")
                    or hybrid.get("features_snapshot_id")
                    or uuid4().hex
                ),
                model_name="hybrid_prediction",
                raw={
                    "hybrid": hybrid,
                    "path": path_payload,
                    "path_error": str(path_error) if path_error else None,
                    "alignment": "hybrid_signal_path_sizing",
                },
                signal_source="hybrid",
                path_expected_return=float(path_ret) if path_ret is not None else None,
                path_target_price=path_metrics.get("target_price"),  # type: ignore[arg-type]
                path_stop_price=path_metrics.get("stop_price"),  # type: ignore[arg-type]
            )

        # Hybrid unavailable: never invent BUY/SELL from the path.
        path_ret = path_metrics.get("expected_return")
        return ForecastResult(
            symbol=ticker,
            signal="HOLD",
            confidence=0.0,
            forecast_horizon=timeframe,
            expected_return=float(path_ret or 0.0),
            downside_risk=float(path_metrics.get("downside_risk") or 0.0),
            forecast_version="hybrid-unavailable",
            generated_at=now,
            features_snapshot_id=uuid4().hex,
            model_name="hybrid_unavailable",
            raw={
                "path": path_payload,
                "path_error": str(path_error) if path_error else None,
                "reason": "calibrated hybrid prediction unavailable; path not used for direction",
                "require_hybrid_signal": self.require_hybrid_signal,
                "alignment": "hybrid_signal_path_sizing",
            },
            signal_source="unavailable",
            path_expected_return=float(path_ret) if path_ret is not None else None,
            path_target_price=path_metrics.get("target_price"),  # type: ignore[arg-type]
            path_stop_price=path_metrics.get("stop_price"),  # type: ignore[arg-type]
        )

    def _hybrid_payload(self, ticker: str) -> dict[str, Any] | None:
        if self.prediction is None:
            return None
        try:
            payload = self.prediction.predict(ticker, horizon="5d")
        except Exception:
            return None
        if not isinstance(payload, dict) or not payload.get("signal"):
            return None
        return payload

    def _path_payload(self, ticker: str, timeframe: str) -> tuple[dict[str, Any] | None, Exception | None]:
        if self.kronos is None:
            return None, None
        try:
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
            return (path if isinstance(path, dict) else None), None
        except Exception as exc:
            return None, exc

    def _spot_price(self, ticker: str, path: dict[str, Any] | None) -> float | None:
        if path:
            hist = path.get("historical") or []
            if isinstance(hist, list) and hist:
                close = hist[-1].get("close") if isinstance(hist[-1], dict) else None
                value = _as_float(close, float("nan"))
                if value == value and value > 0:
                    return value
            forecast_rows = path.get("forecast") or []
            if isinstance(forecast_rows, list) and forecast_rows and isinstance(forecast_rows[0], dict):
                # No spot — leave None
                pass
        if self.alpaca is None:
            return None
        try:
            snap = self.alpaca.snapshot(ticker)
            price = _as_float((snap or {}).get("current_price"), float("nan"))
            return price if price == price and price > 0 else None
        except Exception:
            return None


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
            signal_source="static",
        )
