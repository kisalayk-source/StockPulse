"""Thin FastAPI research server for multi-model forecasts.

Does not replace StockPulse POST /forecast. Run with:

    uvicorn forecasting.api.serve:app --host 127.0.0.1 --port 8001
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from forecasting.core.registry import (
    get_active_models,
    get_ensemble_settings,
    get_model_weights,
    load_config,
)
from forecasting.core.schema import ForecastInput
from forecasting.data.loader import load_ohlcv, load_ohlcv_csv
from forecasting.ensemble.combine import forecast_ensemble

logger = logging.getLogger("forecasting.api")

app = FastAPI(
    title="Kronos Multi-Model Forecasting (research)",
    version="0.1.0",
    description="Research tooling only — not wired to order execution.",
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "models.yaml"


class ForecastRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    horizon: int = Field(default=10, ge=1, le=120)
    context_len: int | None = Field(default=64, ge=8, le=2048)
    timeframe: str = "1Day"
    models: list[str] | None = None  # subset of registry names; None = all active
    csv_path: str | None = None
    strategy: str | None = None


def _result_to_dict(result: Any) -> dict[str, Any]:
    predicted = result.predicted.reset_index(drop=True)
    payload: dict[str, Any] = {
        "model_name": result.model_name,
        "ticker": result.ticker,
        "latency_ms": result.latency_ms,
        "meta": result.meta,
        "predicted": [
            {"close": float(row["close"]), **{k: float(row[k]) for k in row.index if k != "close" and pd.notna(row[k])}}
            for _, row in predicted.iterrows()
        ],
    }
    if result.quantiles:
        payload["quantiles"] = {
            str(q): [{"close": float(v)} for v in frame["close"].tolist()]
            for q, frame in result.quantiles.items()
        }
    return payload


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/forecast")
def forecast(req: ForecastRequest) -> dict[str, Any]:
    """POST /forecast {ticker, horizon, models?} — research multi-model forecast."""
    try:
        cfg = load_config(CONFIG_PATH)
        models = get_active_models(config=cfg)
        weights = get_model_weights(config=cfg)
        ensemble_cfg = get_ensemble_settings(config=cfg)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"config error: {exc}") from exc

    if req.models:
        wanted = {m.lower() for m in req.models}
        models = [m for m in models if m.name.lower() in wanted]
        if not models:
            raise HTTPException(status_code=400, detail=f"no matching models for {req.models}")

    try:
        if req.csv_path:
            ohlcv = load_ohlcv_csv(req.csv_path, ticker=req.ticker.upper())
        else:
            ohlcv = load_ohlcv(
                req.ticker.upper(),
                timeframe=req.timeframe,
                limit=int(req.context_len or 64) + 32,
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"data error: {exc}") from exc

    inp = ForecastInput(
        ticker=req.ticker.upper(),
        ohlcv=ohlcv,
        horizon=req.horizon,
        context_len=req.context_len,
        timeframe=req.timeframe,
    )
    strategy = req.strategy or str(ensemble_cfg.get("strategy") or "weighted_average")
    # Research API uses weighted_average unless inverse_error history exists (not persisted here)
    if strategy == "inverse_error":
        strategy = "weighted_average"

    per_model, ensemble = forecast_ensemble(
        models,
        inp,
        strategy=strategy,
        weights=weights,
    )
    return {
        "ticker": req.ticker.upper(),
        "horizon": req.horizon,
        "strategy": strategy,
        "models": [_result_to_dict(r) for r in per_model],
        "ensemble": _result_to_dict(ensemble) if ensemble else None,
        "disclaimer": "Research output only. Not investment advice. No order execution.",
    }
