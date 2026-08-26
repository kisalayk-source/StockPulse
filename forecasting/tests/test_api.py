"""Research API smoke tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from forecasting.api.serve import app
from forecasting.core.base import ForecastModel
from forecasting.core.schema import ForecastInput, ForecastResult
import forecasting.api.serve as serve_mod

FIXTURE = Path(__file__).parent / "fixtures" / "sample_ohlcv.csv"


class _ApiStub(ForecastModel):
    name = "api_stub"

    def load(self) -> None:
        return None

    def supports(self, inp: ForecastInput) -> bool:
        return True

    def predict(self, inp: ForecastInput) -> ForecastResult:
        last = float(inp.ohlcv["close"].iloc[-1])
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=pd.DataFrame({"close": [last] * inp.horizon}),
            meta={"checkpoint": "stub"},
        )


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_forecast_with_csv(monkeypatch):
    monkeypatch.setattr(serve_mod, "get_active_models", lambda config=None: [_ApiStub()])
    monkeypatch.setattr(serve_mod, "get_model_weights", lambda config=None: {"api_stub": 1.0})
    monkeypatch.setattr(
        serve_mod,
        "get_ensemble_settings",
        lambda config=None: {"strategy": "weighted_average"},
    )
    monkeypatch.setattr(serve_mod, "load_config", lambda path=None: {"models": {}})

    client = TestClient(app)
    resp = client.post(
        "/forecast",
        json={
            "ticker": "TEST",
            "horizon": 3,
            "context_len": 40,
            "csv_path": str(FIXTURE),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ticker"] == "TEST"
    assert len(body["models"]) == 1
    assert body["ensemble"] is not None
    assert "disclaimer" in body
