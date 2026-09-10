"""Hybrid directional prediction service wrapping ``ml.PredictionEngine``."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from app.config import ROOT_DIR, Settings


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


class PredictionService:
    def __init__(self, settings: Settings, alpaca: Any) -> None:
        self.settings = settings
        self.alpaca = alpaca
        _ensure_repo_root_on_path()
        from ml.service import PredictionEngine

        self.engine = PredictionEngine(root_dir=ROOT_DIR)
        self.enabled = bool(getattr(settings, "prediction_enabled", True))
        self._dependency_error = _xgboost_import_error()

    def _require_ready(self) -> None:
        if not self.enabled:
            raise RuntimeError("hybrid prediction is disabled")
        if self._dependency_error:
            raise RuntimeError(self._dependency_error)

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

    def predict(self, ticker: str, *, horizon: str = "5d", retrain: bool = False) -> dict[str, Any]:
        self._require_ready()
        lookback = int(self.engine.config.get("prediction", {}).get("lookback_bars", 400))
        bars = self._fetch_daily_bars(ticker, limit=lookback)
        return self.engine.predict_from_bars(ticker, bars, horizon=horizon, retrain=retrain)

    def features(self, ticker: str) -> dict[str, Any]:
        lookback = int(self.engine.config.get("prediction", {}).get("lookback_bars", 400))
        bars = self._fetch_daily_bars(ticker, limit=lookback)
        return self.engine.features_from_bars(ticker, bars)

    def signals(self, ticker: str, *, horizon: str = "5d") -> dict[str, Any]:
        result = self.predict(ticker, horizon=horizon)
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

    def risk(self, ticker: str, *, horizon: str = "5d") -> dict[str, Any]:
        result = self.predict(ticker, horizon=horizon)
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "horizon": result["horizon"],
            "risk": result["risk"],
            "risk_score": result["risk_score"],
            "confidence": result["confidence"],
            "note": "Signal risk engine (ml/risk); independent from order risk gates.",
        }

    def explanation(self, ticker: str, *, horizon: str = "5d") -> dict[str, Any]:
        result = self.predict(ticker, horizon=horizon)
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "horizon": result["horizon"],
            "signal": result["signal"],
            "explanation": result["explanation"],
        }
