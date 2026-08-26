"""Amazon Chronos ForecastModel adapter (univariate close)."""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd

from forecasting.core.base import ForecastModel
from forecasting.core.schema import ForecastInput, ForecastResult

logger = logging.getLogger("forecasting.adapters.chronos")

DEFAULT_CHECKPOINT = "amazon/chronos-t5-small"


class ChronosAdapter(ForecastModel):
    name = "chronos"

    def __init__(
        self,
        *,
        checkpoint: str = DEFAULT_CHECKPOINT,
        device: str = "cpu",
        pipeline: Any | None = None,
        num_samples: int = 20,
    ) -> None:
        self.checkpoint = checkpoint
        self.device = device
        self.num_samples = int(num_samples)
        self._pipeline = pipeline
        self._loaded = pipeline is not None

    def load(self) -> None:
        if self._loaded and self._pipeline is not None:
            return
        try:
            import torch
            from chronos import ChronosPipeline
        except ImportError as exc:
            raise ImportError(
                "Chronos extras not installed. "
                "pip install -r forecasting/requirements-chronos.txt"
            ) from exc

        self._pipeline = ChronosPipeline.from_pretrained(
            self.checkpoint,
            device_map=self.device,
            torch_dtype=torch.bfloat16 if self.device != "cpu" else torch.float32,
        )
        self._loaded = True
        logger.info("Loaded Chronos checkpoint %s", self.checkpoint)

    def supports(self, inp: ForecastInput) -> bool:
        if inp.horizon < 1:
            return False
        if "close" not in inp.ohlcv.columns:
            return False
        context = inp.context_len if inp.context_len is not None else len(inp.ohlcv)
        if context < 8 or len(inp.ohlcv) < 8:
            return False
        # Chronos-t5 context is large; refuse only pathological sizes without truncating.
        if context > 4096:
            logger.warning("ChronosAdapter rejects context %s > 4096", context)
            return False
        return True

    def predict(self, inp: ForecastInput) -> ForecastResult:
        if not self.supports(inp):
            raise ValueError("ChronosAdapter does not support this input")
        if not self._loaded:
            self.load()
        assert self._pipeline is not None

        import torch

        context = inp.context_len if inp.context_len is not None else len(inp.ohlcv)
        closes = inp.ohlcv["close"].astype(float).tail(context).to_numpy()
        context_tensor = torch.tensor(closes, dtype=torch.float32)

        start = time.perf_counter()
        forecast = self._pipeline.predict(
            context_tensor,
            prediction_length=inp.horizon,
            num_samples=self.num_samples,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        # forecast shape: (1, num_samples, horizon) or (num_samples, horizon)
        arr = forecast.detach().cpu().numpy() if hasattr(forecast, "detach") else np.asarray(forecast)
        if arr.ndim == 3:
            samples = arr[0]
        elif arr.ndim == 2:
            samples = arr
        else:
            samples = arr.reshape(1, -1)

        median = np.median(samples, axis=0)
        q10 = np.quantile(samples, 0.1, axis=0)
        q90 = np.quantile(samples, 0.9, axis=0)

        predicted = pd.DataFrame({"close": median.astype(float)})
        quantiles = {
            0.1: pd.DataFrame({"close": q10.astype(float)}),
            0.9: pd.DataFrame({"close": q90.astype(float)}),
        }
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=predicted,
            quantiles=quantiles,
            latency_ms=latency_ms,
            meta={
                "checkpoint": self.checkpoint,
                "device": self.device,
                "num_samples": self.num_samples,
                "context_used": len(closes),
                "series": "close",
            },
        )
