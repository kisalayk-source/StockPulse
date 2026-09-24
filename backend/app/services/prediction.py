"""Hybrid directional prediction service wrapping ``ml.PredictionEngine``."""

from __future__ import annotations

import asyncio
import contextvars
import sys
import time
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from app.config import ROOT_DIR, Settings

# Per-call only. predict() runs on the threadpool, so a field on the shared service races.
_path_use_cache: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "prediction_path_use_cache",
    default=True,
)


def _ensure_repo_root_on_path() -> None:
    root = str(ROOT_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)


def _xgboost_import_error() -> str | None:
    try:
        import xgboost  # noqa: F401
    except ImportError as exc:
        missing = getattr(exc, "name", None) or "xgboost"
        return (
            f"hybrid prediction requires {missing}; "
            "install backend/requirements.txt and restart the API"
        )
    return None


def serialize_normalized_event(event: Any) -> dict[str, Any]:
    """Convert a ``NormalizedEvent`` (or duck-typed object) to a plain feature dict."""

    def _date(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        return text[:10] if text else None

    meta = getattr(event, "metadata", None)
    if not isinstance(meta, dict):
        meta = {}
    data_ts = getattr(event, "data_timestamp", None)
    return {
        "event_id": getattr(event, "event_id", None),
        "source": getattr(event, "source", None),
        "accession_number": getattr(event, "accession_number", None),
        "filing_date": _date(getattr(event, "filing_date", None)),
        "reporting_period": _date(getattr(event, "reporting_period", None)),
        "published_at": _date(getattr(event, "filing_date", None) or getattr(event, "reporting_period", None)),
        "event_type": getattr(event, "event_type", None),
        "component": getattr(event, "component", None),
        "signal_label": getattr(event, "signal_label", None),
        "data_timestamp": data_ts.isoformat() if isinstance(data_ts, datetime) else data_ts,
        "ticker": getattr(event, "ticker", None),
        "polarity": float(getattr(event, "polarity", 0.0) or 0.0),
        "metadata": dict(meta),
    }


def _copy_feature_value(value: Any) -> Any:
    if isinstance(value, list):
        return [dict(item) if isinstance(item, dict) else item for item in value]
    if isinstance(value, dict):
        return dict(value)
    return value


class PredictionService:
    def __init__(
        self,
        settings: Settings,
        alpaca: Any,
        kronos: Any | None = None,
        finnhub: Any | None = None,
        sec: Any | None = None,
        government: Any | None = None,
    ) -> None:
        self.settings = settings
        self.alpaca = alpaca
        self.kronos = kronos
        self.finnhub = finnhub
        self.sec = sec
        self.government = government
        self._feature_input_cache: dict[tuple[str, str], tuple[float, Any]] = {}
        _ensure_repo_root_on_path()
        from ml.config import horizon_to_bars
        from ml.service import PredictionEngine

        self.engine = PredictionEngine(root_dir=ROOT_DIR)
        self.enabled = bool(getattr(settings, "prediction_enabled", True))
        self._dependency_error = _xgboost_import_error()
        self._horizon_to_bars = horizon_to_bars
        if kronos is not None:
            self.bind_kronos(kronos)

    def bind_kronos(self, kronos: Any) -> None:
        """Attach KronosService so directional adapter can request path forecasts."""
        self.kronos = kronos
        self.engine.set_path_forecast_fn(self._path_forecast)

    def _path_forecast(self, symbol: str, horizon_key: str, ohlcv: pd.DataFrame) -> dict[str, Any] | None:
        if self.kronos is None:
            return None
        horizon_bars = int(self._horizon_to_bars(horizon_key))
        bars: list[dict[str, Any]] = []
        for ts, row in ohlcv.iterrows():
            bars.append(
                {
                    "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0) or 0),
                }
            )
        engine = "ensemble"
        kronos_cfg = self.engine.config.get("models", {}).get("kronos", {}) or {}
        if kronos_cfg.get("path_engine"):
            engine = str(kronos_cfg.get("path_engine"))
        return self.kronos.forecast(
            symbol.upper(),
            "long",
            timeframe="1Day",
            context=int(kronos_cfg.get("context", 64) or 64),
            horizon=max(1, horizon_bars),
            bars=bars,
            use_cache=_path_use_cache.get(),
            evaluate=False,
            engine=engine,
        )

    def _require_ready(self) -> None:
        if not self.enabled:
            raise RuntimeError("hybrid prediction is disabled")
        if self._dependency_error:
            raise RuntimeError(self._dependency_error)

    def _feature_flags(self) -> dict[str, bool]:
        flags = self.engine.config.get("features") or {}
        return {
            "sec": bool(flags.get("sec", False)),
            "fundamentals": bool(flags.get("fundamentals", False)),
            "government": bool(flags.get("government", False)),
        }

    def load_sec_event_dicts(self, session: Any, ticker: str) -> list[dict[str, Any]]:
        """Load already-synced SEC events from SQLite (no EDGAR sync)."""
        if self.sec is None or session is None:
            return []
        try:
            events = self.sec.load_normalized_events(session, ticker.upper())
        except Exception:
            return []
        return [serialize_normalized_event(event) for event in events or []]

    def load_government_event_dicts(self, session: Any, ticker: str) -> list[dict[str, Any]]:
        """Load confident government events already stored for the ticker."""
        if self.government is None or session is None:
            return []
        try:
            return self.government.events_as_dicts(session, ticker.upper())
        except Exception:
            return []

    def government_config(self) -> dict[str, Any]:
        if self.government is None:
            return {}
        return dict(getattr(self.government, "config", None) or {})

    async def load_fundamentals_metrics(self, ticker: str) -> dict[str, Any]:
        """Fetch Finnhub extended fundamentals; empty dict on failure."""
        if self.finnhub is None:
            return {}
        try:
            metrics = await self.finnhub.extended_fundamentals(ticker.upper())
        except Exception:
            return {}
        return dict(metrics or {})

    _FEATURE_INPUT_TTL_SECONDS = 300.0

    def _feature_cache_get(self, kind: str, ticker: str) -> tuple[bool, Any]:
        key = (kind, ticker.upper())
        hit = self._feature_input_cache.get(key)
        if hit is None:
            return False, None
        stored_at, value = hit
        if time.monotonic() - stored_at > self._FEATURE_INPUT_TTL_SECONDS:
            self._feature_input_cache.pop(key, None)
            return False, None
        return True, _copy_feature_value(value)

    def _feature_cache_put(self, kind: str, ticker: str, value: Any) -> Any:
        stored = _copy_feature_value(value)
        self._feature_input_cache[(kind, ticker.upper())] = (time.monotonic(), stored)
        return _copy_feature_value(stored)

    def _load_fundamentals_sync(self, ticker: str) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.load_fundamentals_metrics(ticker))
        raise RuntimeError("fundamentals cache miss from a running event loop")

    def _cached_sec(self, session: Any, ticker: str) -> list[dict[str, Any]]:
        found, value = self._feature_cache_get("sec", ticker)
        if found:
            return value
        return self._feature_cache_put("sec", ticker, self.load_sec_event_dicts(session, ticker))

    def _cached_government(self, session: Any, ticker: str) -> list[dict[str, Any]]:
        found, value = self._feature_cache_get("government", ticker)
        if found:
            return value
        return self._feature_cache_put("government", ticker, self.load_government_event_dicts(session, ticker))

    def _cached_fundamentals(self, ticker: str, metrics: dict[str, Any]) -> dict[str, Any]:
        return self._feature_cache_put("fundamentals", ticker, metrics)

    def cached_feature_inputs(self, session: Any, ticker: str) -> dict[str, Any]:
        """SEC, fundamentals, and government inputs. Empty results stay cached for 300s."""
        flags = self._feature_flags()
        out: dict[str, Any] = {}
        if flags.get("sec"):
            out["sec_events"] = self._cached_sec(session, ticker)
        if flags.get("fundamentals"):
            found, metrics = self._feature_cache_get("fundamentals", ticker)
            out["fundamentals_metrics"] = metrics if found else self._cached_fundamentals(
                ticker, self._load_fundamentals_sync(ticker)
            )
        if flags.get("government"):
            out["government_events"] = self._cached_government(session, ticker)
            out["government_config"] = self.government_config()
        return out

    async def cached_feature_inputs_async(self, session: Any, ticker: str) -> dict[str, Any]:
        flags = self._feature_flags()
        out: dict[str, Any] = {}
        if flags.get("sec"):
            out["sec_events"] = self._cached_sec(session, ticker)
        if flags.get("fundamentals"):
            found, metrics = self._feature_cache_get("fundamentals", ticker)
            if found:
                out["fundamentals_metrics"] = metrics
            else:
                out["fundamentals_metrics"] = self._cached_fundamentals(
                    ticker, await self.load_fundamentals_metrics(ticker)
                )
        if flags.get("government"):
            out["government_events"] = self._cached_government(session, ticker)
            out["government_config"] = self.government_config()
        return out

    def _annual_revenue_from_metrics(self, metrics: dict[str, Any] | None) -> float | None:
        if not metrics:
            return None
        for key in ("revenue", "annual_revenue", "revenueTTM", "market_cap"):
            value = metrics.get(key)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                return number
        return None

    def _fetch_daily_bars(self, ticker: str, limit: int = 400) -> list[dict[str, Any]]:
        bars = self.alpaca.bars(
            ticker.upper(),
            "1Day",
            None,
            datetime.now(timezone.utc),
            limit,
        )
        # Alpaca returns newest-first; engine sorts ascending.
        return list(bars or [])

    def predict(
        self,
        ticker: str,
        *,
        horizon: str = "5d",
        retrain: bool = False,
        refresh: bool = False,
        sec_events: list[dict[str, Any]] | None = None,
        fundamentals_metrics: dict[str, Any] | None = None,
        government_events: list[dict[str, Any]] | None = None,
        annual_revenue: float | None = None,
        government_config: dict[str, Any] | None = None,
        position_concentration: float | None = None,
    ) -> dict[str, Any]:
        self._require_ready()
        lookback = int(self.engine.config.get("prediction", {}).get("lookback_bars", 400))
        bars = self._fetch_daily_bars(ticker, limit=lookback)
        token = _path_use_cache.set(not refresh)
        try:
            return self.engine.predict_from_bars(
                ticker,
                bars,
                horizon=horizon,
                retrain=retrain,
                sec_events=sec_events,
                fundamentals_metrics=fundamentals_metrics,
                government_events=government_events,
                annual_revenue=annual_revenue
                if annual_revenue is not None
                else self._annual_revenue_from_metrics(fundamentals_metrics),
                government_config=government_config if government_config is not None else self.government_config(),
                position_concentration=position_concentration,
            )
        finally:
            _path_use_cache.reset(token)

    def features(
        self,
        ticker: str,
        *,
        sec_events: list[dict[str, Any]] | None = None,
        fundamentals_metrics: dict[str, Any] | None = None,
        government_events: list[dict[str, Any]] | None = None,
        annual_revenue: float | None = None,
        government_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        lookback = int(self.engine.config.get("prediction", {}).get("lookback_bars", 400))
        bars = self._fetch_daily_bars(ticker, limit=lookback)
        return self.engine.features_from_bars(
            ticker,
            bars,
            sec_events=sec_events,
            fundamentals_metrics=fundamentals_metrics,
            government_events=government_events,
            annual_revenue=annual_revenue
            if annual_revenue is not None
            else self._annual_revenue_from_metrics(fundamentals_metrics),
            government_config=government_config if government_config is not None else self.government_config(),
        )

    def signals(self, ticker: str, *, horizon: str = "5d", **kwargs: Any) -> dict[str, Any]:
        result = self.predict(ticker, horizon=horizon, **kwargs)
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "horizon": result["horizon"],
            "signal": result["signal"],
            "probability": result["probability"],
            "risk_score": result["risk_score"],
            "confidence": result["confidence"],
            "decision": result["decision"],
        }

    def risk(self, ticker: str, *, horizon: str = "5d", **kwargs: Any) -> dict[str, Any]:
        result = self.predict(ticker, horizon=horizon, **kwargs)
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "horizon": result["horizon"],
            "risk": result["risk"],
            "risk_score": result["risk_score"],
            "confidence": result["confidence"],
            "note": "Signal risk engine (ml/risk); independent from order risk gates.",
        }

    def explanation(self, ticker: str, *, horizon: str = "5d", **kwargs: Any) -> dict[str, Any]:
        result = self.predict(ticker, horizon=horizon, **kwargs)
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "horizon": result["horizon"],
            "signal": result["signal"],
            "explanation": result["explanation"],
        }
