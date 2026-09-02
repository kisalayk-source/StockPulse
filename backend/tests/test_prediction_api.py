"""Prediction engine + API smoke tests."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.db import reset_db_state
from app.dependencies import Services
from app.main import create_app

from ml.registry import ModelRegistry
from ml.service import PredictionEngine


class FakeSec:
    async def accumulation_for_ticker(self, session, ticker, alpaca, finnhub, sync=True):
        return {"ticker": ticker.upper(), "score": 50.0, "signal": "NEUTRAL"}

    def sec_intelligence(self, session, ticker, accumulation):
        return {"ticker": ticker.upper(), "accumulation": accumulation}

    async def sync_ticker(self, *args, **kwargs):
        return None

    def scan_status(self):
        return {"status": "idle", "scanned": 0, "total": 0, "errors": []}

    def start_accumulation_scan(self, services, *, refresh=False):
        return {"status": "ready", "scanned": 0, "total": 0, "errors": []}

    def maybe_auto_scan(self, session, services):
        return None


class FakeFinnhub:
    async def search(self, query: str) -> list[dict]:
        return []

    async def company_profile(self, symbol: str) -> dict:
        return {}

    async def extended_fundamentals(self, symbol: str) -> dict:
        return {}

    async def company_news(self, symbol: str, limit: int) -> list[dict]:
        return []

    async def fundamentals(self, symbol: str) -> dict:
        return {}

    async def news_sentiment(self, symbol: str) -> dict:
        return {"label": "neutral", "bullish_percent": None, "bearish_percent": None, "score": None}


class FakeKronos:
    def forecast(self, *args, **kwargs) -> dict:
        return {"symbol": "AAPL", "forecast": [], "trend": {"direction": "flat"}}

    def scan_movers(self, limit: int = 50, refresh: bool = False) -> dict:
        return {"movers": [], "scanned": 0}


def register_and_headers(client: TestClient) -> dict[str, str]:
    address = f"user-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": address, "password": "password123"},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    saved = client.put(
        "/api/v1/auth/alpaca",
        headers=headers,
        json={"mode": "paper", "key_id": "PKTESTKEY123456", "secret": "secretsecret12"},
    )
    assert saved.status_code == 200, saved.text
    return headers


def _bars(n: int = 320, seed: int = 3) -> list[dict]:
    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    close = 100.0
    rows = []
    for i in range(n):
        close *= 1 + float(rng.normal(0.0004, 0.012))
        high = close * 1.01
        low = close * 0.99
        open_ = close * (1 + float(rng.normal(0, 0.002)))
        rows.append(
            {
                "timestamp": (start + timedelta(days=i)).isoformat(),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": float(rng.integers(1_000_000, 4_000_000)),
            }
        )
    return list(reversed(rows))  # newest first like Alpaca


class RichFakeAlpaca:
    def __init__(self) -> None:
        self._bars = _bars()

    def bars(self, symbol: str, timeframe: str, start, end, limit: int) -> list[dict]:
        return self._bars[:limit]

    def search_assets(self, query: str, mode: str) -> list[dict]:
        return [{"symbol": "AAPL", "name": "Apple Inc.", "tradable": True}]

    def snapshot(self, symbol: str) -> dict:
        return {
            "symbol": symbol.upper(),
            "current_price": 200.0,
            "timestamp": "2026-08-12T18:00:00+00:00",
            "session": "regular",
            "daily": {"open": 198.0, "high": 201.0, "low": 197.0, "close": 200.0},
            "previous_daily": None,
        }

    def news(self, symbol: str, limit: int) -> list[dict]:
        return []

    def account(self, mode: str) -> dict:
        return {"id": "account", "mode": mode}

    def realized_pl(self, mode: str) -> dict:
        return {"realized_pl": 0.0, "fill_count": 0, "as_of": "2026-08-25T12:00:00+00:00"}

    def positions(self, mode: str) -> list[dict]:
        return []

    def orders(self, mode: str, status: str, limit: int) -> list[dict]:
        return []

    def option_contracts(self, *args, **kwargs) -> list[dict]:
        return []

    def option_chain(self, *args, **kwargs) -> dict:
        return {}

    def submit_equity_order(self, order) -> dict:
        return {"id": "equity-order", "status": "accepted"}

    def submit_option_order(self, order) -> dict:
        return {"id": "option-order", "status": "accepted"}

    def preview_order(self, order) -> dict:
        return {"ok": True, "estimated_cost": 200.0, "warnings": [], "risk": {"new_buys_halted": False}}

    def cancel_order(self, order_id: str, mode: str) -> dict:
        return {"id": order_id, "status": "cancel_requested"}

    def replace_order(self, order_id: str, replacement) -> dict:
        return {"id": order_id, "status": "replaced"}

    def market_clock(self, mode: str = "paper") -> dict:
        return {
            "is_open": True,
            "session": "regular",
            "timestamp": "2026-08-12T14:30:00+00:00",
            "next_open": "2026-08-13T13:30:00+00:00",
            "next_close": "2026-08-12T20:00:00+00:00",
        }


class FakePrediction:
    def predict(self, ticker: str, *, horizon: str = "5d", retrain: bool = False) -> dict:
        return {
            "ticker": ticker.upper(),
            "timestamp": "2026-08-12T18:00:00+00:00",
            "horizon": horizon,
            "signal": "BUY",
            "probability": 0.72,
            "raw_probability": 0.72,
            "expected_return": None,
            "risk_score": 0.31,
            "confidence": 0.76,
            "prediction_probability": 0.72,
            "model_confidence": 1.0,
            "data_confidence": 1.0,
            "signal_confidence": 0.76,
            "model_predictions": {"xgboost": 0.72},
            "model_versions": {"xgboost": "1.0"},
            "model_agreement": 1.0,
            "feature_version": "1.0.0",
            "feature_snapshot": {"ticker": ticker.upper(), "technical": {"rsi": 55.0}},
            "training_cutoff": "2026-08-12T18:00:00+00:00",
            "decision": {"signal": "BUY", "probability": 0.72},
            "risk": {"risk_score": 0.31, "confidence_score": 0.76},
            "market_regime": {"regime": "BULL"},
            "explanation": {
                "text": f"{ticker.upper()} is rated BUY with a 72% estimated probability of positive movement over the {horizon} horizon.",
                "provider": "template",
                "structured": {},
            },
            "latency_ms": 1.2,
        }

    def features(self, ticker: str) -> dict:
        return {"ticker": ticker.upper(), "technical": {"rsi": 55.0}, "feature_version": "1.0.0"}

    def signals(self, ticker: str, *, horizon: str = "5d") -> dict:
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

    def risk(self, ticker: str, *, horizon: str = "5d") -> dict:
        result = self.predict(ticker, horizon=horizon)
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "horizon": result["horizon"],
            "risk": result["risk"],
            "risk_score": result["risk_score"],
            "confidence": result["confidence"],
            "note": "Signal risk engine",
        }

    def explanation(self, ticker: str, *, horizon: str = "5d") -> dict:
        result = self.predict(ticker, horizon=horizon)
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "horizon": result["horizon"],
            "signal": result["signal"],
            "explanation": result["explanation"],
        }


def settings(**overrides) -> Settings:
    defaults = {"database_url": "sqlite://"}
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def make_client(prediction=None) -> TestClient:
    reset_db_state()
    config = settings()
    alpaca = RichFakeAlpaca()
    services = Services(
        config,
        alpaca,
        FakeFinnhub(),
        FakeKronos(),
        FakeSec(),
        prediction=prediction or FakePrediction(),
    )
    return TestClient(create_app(config, services))


def test_prediction_api_endpoints() -> None:
    with make_client() as client:
        headers = register_and_headers(client)
        pred = client.get("/api/v1/stocks/AAPL/prediction", headers=headers, params={"horizon": "5d"})
        assert pred.status_code == 200, pred.text
        body = pred.json()
        assert body["ticker"] == "AAPL"
        assert body["signal"] == "BUY"
        assert body["probability"] == 0.72
        assert "xgboost" in body["model_predictions"]

        features = client.get("/api/v1/stocks/AAPL/features", headers=headers)
        assert features.status_code == 200
        signals = client.get("/api/v1/stocks/AAPL/signals", headers=headers)
        assert signals.status_code == 200
        risk = client.get("/api/v1/stocks/AAPL/risk", headers=headers)
        assert risk.status_code == 200
        explanation = client.get("/api/v1/stocks/AAPL/explanation", headers=headers)
        assert explanation.status_code == 200
        assert "72%" in explanation.json()["explanation"]["text"]


def test_prediction_engine_end_to_end(tmp_path: Path) -> None:
    pytest.importorskip("xgboost")
    engine = PredictionEngine(
        config={
            "prediction": {
                "horizons": ["1d", "5d", "20d"],
                "return_threshold": 0.0,
                "lookback_bars": 400,
                "min_train_rows": 60,
                "feature_version": "1.0.0",
            },
            "models": {
                "xgboost": {
                    "enabled": True,
                    "weight": 1.0,
                    "params": {"n_estimators": 20, "max_depth": 3, "n_jobs": 1, "random_state": 0},
                },
                "kronos": {"enabled": False},
                "lightgbm": {"enabled": False},
            },
            "ensemble": {"strategy": "equal_weight"},
            "calibration": {"method": "identity"},
            "decision": {
                "buy_probability": 0.65,
                "strong_buy_probability": 0.80,
                "sell_probability": 0.35,
                "strong_sell_probability": 0.20,
                "minimum_model_agreement": 0.60,
            },
            "risk": {"enabled": False},
            "llm": {"enabled": False},
            "registry": {"store_dir": str(tmp_path / "registry")},
        },
        registry=ModelRegistry(tmp_path / "registry"),
        root_dir=ROOT,
    )
    result = engine.predict_from_bars("AAPL", _bars(320), horizon="5d", retrain=True)
    assert result["ticker"] == "AAPL"
    assert result["signal"] in {"BUY", "STRONG BUY", "HOLD", "SELL", "STRONG SELL"}
    assert 0.0 <= result["probability"] <= 1.0
    assert result["feature_version"] == "1.0.0"
    assert "timestamp" in result
    assert "training_cutoff" in result
    assert result["feature_snapshot"]["technical"]
