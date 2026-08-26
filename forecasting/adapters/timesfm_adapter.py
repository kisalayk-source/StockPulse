"""Google TimesFM ForecastModel adapter (univariate close, zero-shot)."""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd

from forecasting.core.base import ForecastModel
from forecasting.core.schema import ForecastInput, ForecastResult

logger = logging.getLogger("forecasting.adapters.timesfm")

DEFAULT_CHECKPOINT = "google/timesfm-1.0-200m-pytorch"


class TimesFMAdapter(ForecastModel):
    name = "timesfm"

    def __init__(
        self,
        *,
        checkpoint: str = DEFAULT_CHECKPOINT,
        horizon_per_call: int | None = None,
        model: Any | None = None,
    ) -> None:
        self.checkpoint = checkpoint
        self.horizon_per_call = horizon_per_call
        self._model = model
        self._loaded = model is not None

    def load(self) -> None:
        if self._loaded and self._model is not None:
            return
        try:
            import timesfm
        except ImportError as exc:
            raise ImportError(
                "TimesFM extras not installed. "
                "pip install -r forecasting/requirements-timesfm.txt"
            ) from exc

        # API varies by timesfm version; support common entry points.
        if hasattr(timesfm, "TimesFm"):
            hparams = getattr(timesfm, "TimesFmHparams", None)
            checkpoint_cls = getattr(timesfm, "TimesFmCheckpoint", None)
            if hparams is not None and checkpoint_cls is not None:
                self._model = timesfm.TimesFm(
                    hparams=hparams(
                        backend="cpu",
                        per_core_batch_size=1,
                        horizon_len=int(self.horizon_per_call or 128),
                    ),
                    checkpoint=checkpoint_cls(huggingface_repo_id=self.checkpoint),
                )
            else:
                self._model = timesfm.TimesFm()
                if hasattr(self._model, "load_from_checkpoint"):
                    self._model.load_from_checkpoint(repo_id=self.checkpoint)
        else:
            raise ImportError("timesfm package loaded but TimesFm class not found")
        self._loaded = True
        logger.info("Loaded TimesFM checkpoint %s", self.checkpoint)

    def supports(self, inp: ForecastInput) -> bool:
        if inp.horizon < 1 or "close" not in inp.ohlcv.columns:
            return False
        context = inp.context_len if inp.context_len is not None else len(inp.ohlcv)
        if context < 32 or len(inp.ohlcv) < 32:
            return False
        if context > 2048:
            logger.warning("TimesFMAdapter rejects context %s > 2048", context)
            return False
        return True

    def predict(self, inp: ForecastInput) -> ForecastResult:
        if not self.supports(inp):
            raise ValueError("TimesFMAdapter does not support this input")
        if not self._loaded:
            self.load()
        assert self._model is not None

        context = inp.context_len if inp.context_len is not None else len(inp.ohlcv)
        closes = inp.ohlcv["close"].astype(float).tail(context).to_numpy()

        start = time.perf_counter()
        point_forecast, _quantile_forecast = self._forecast(closes, inp.horizon)
        latency_ms = (time.perf_counter() - start) * 1000.0

        predicted = pd.DataFrame({"close": np.asarray(point_forecast, dtype=float)[: inp.horizon]})
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=predicted,
            latency_ms=latency_ms,
            meta={
                "checkpoint": self.checkpoint,
                "context_used": len(closes),
                "series": "close",
            },
        )

    def _forecast(self, closes: np.ndarray, horizon: int) -> tuple[np.ndarray, Any]:
        model = self._model
        if hasattr(model, "forecast"):
            result = model.forecast([closes], freq=[0])
            if isinstance(result, tuple) and len(result) >= 1:
                point = np.asarray(result[0][0])
                quant = result[1] if len(result) > 1 else None
                return point[:horizon], quant
            arr = np.asarray(result)
            return arr.reshape(-1)[:horizon], None
        if callable(model):
            out = model(closes, horizon)
            return np.asarray(out).reshape(-1)[:horizon], None
        raise RuntimeError("TimesFM model has no forecast() method")
