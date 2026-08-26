"""Kronos ForecastModel adapter."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

from forecasting.adapters._timestamps import future_timestamps
from forecasting.core.base import ForecastModel
from forecasting.core.schema import CANONICAL_OHLCV_COLUMNS, ForecastInput, ForecastResult

logger = logging.getLogger("forecasting.adapters.kronos")

SIZE_PRESETS = {
    "mini": {
        "model_id": "NeoQuasar/Kronos-mini",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 2048,
    },
    "small": {
        "model_id": "NeoQuasar/Kronos-small",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
    },
    "base": {
        "model_id": "NeoQuasar/Kronos-base",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
    },
}


class KronosAdapter(ForecastModel):
    name = "kronos"

    def __init__(
        self,
        *,
        size: str = "small",
        sample_count: int = 1,
        model_id: str | None = None,
        tokenizer_id: str | None = None,
        max_context: int | None = None,
        device: str | None = None,
        temperature: float = 1.0,
        top_k: int = 0,
        top_p: float = 0.9,
        predictor: Any | None = None,
    ) -> None:
        preset = SIZE_PRESETS.get(size, SIZE_PRESETS["small"])
        self.size = size if size in SIZE_PRESETS else "small"
        self.model_id = model_id or preset["model_id"]
        self.tokenizer_id = tokenizer_id or preset["tokenizer_id"]
        self.max_context = int(max_context or preset["max_context"])
        self.sample_count = int(sample_count)
        self.device = device
        self.temperature = temperature
        self.top_k = top_k
        self.top_p = top_p
        self._predictor = predictor
        self._loaded = predictor is not None

    def load(self) -> None:
        if self._loaded and self._predictor is not None:
            return
        root = str(Path(__file__).resolve().parents[2])
        if root not in sys.path:
            sys.path.insert(0, root)
        from model import Kronos, KronosPredictor, KronosTokenizer

        tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_id)
        model = Kronos.from_pretrained(self.model_id)
        tokenizer.eval()
        model.eval()
        self._predictor = KronosPredictor(
            model,
            tokenizer,
            device=self.device,
            max_context=self.max_context,
        )
        self._loaded = True
        logger.info("Loaded Kronos %s (%s)", self.size, self.model_id)

    def supports(self, inp: ForecastInput) -> bool:
        if inp.horizon < 1:
            return False
        missing = [c for c in CANONICAL_OHLCV_COLUMNS if c not in inp.ohlcv.columns]
        if missing:
            return False
        requested = inp.context_len if inp.context_len is not None else len(inp.ohlcv)
        if requested > self.max_context:
            logger.warning(
                "KronosAdapter rejects context %s > max_context %s (no silent truncate)",
                requested,
                self.max_context,
            )
            return False
        if len(inp.ohlcv) < 2:
            return False
        return True

    def predict(self, inp: ForecastInput) -> ForecastResult:
        if not self.supports(inp):
            raise ValueError(
                f"KronosAdapter does not support input "
                f"(len={len(inp.ohlcv)}, horizon={inp.horizon}, max_context={self.max_context})"
            )
        if not self._loaded:
            self.load()
        assert self._predictor is not None

        requested = inp.context_len if inp.context_len is not None else len(inp.ohlcv)
        context = min(requested, len(inp.ohlcv), self.max_context)
        history = inp.ohlcv.tail(context).copy()
        if len(history) < 2:
            raise ValueError("KronosAdapter requires at least 2 historical bars")
        frame = history[list(CANONICAL_OHLCV_COLUMNS)].astype(float)
        frame["amount"] = frame["volume"] * frame[["open", "high", "low", "close"]].mean(axis=1)

        x_ts = pd.Series(history.index, name="timestamps")
        y_idx = future_timestamps(
            history.index[-1].to_pydatetime(),
            inp.timeframe,
            inp.horizon,
        )
        if len(y_idx) != inp.horizon:
            raise ValueError(
                f"future timestamp length {len(y_idx)} != horizon {inp.horizon}"
            )
        y_ts = pd.Series(y_idx, name="timestamps")

        start = time.perf_counter()
        predicted = self._predictor.predict(
            frame,
            x_ts,
            y_ts,
            pred_len=inp.horizon,
            T=self.temperature,
            top_k=self.top_k,
            top_p=self.top_p,
            sample_count=self.sample_count,
            verbose=False,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        if not isinstance(predicted, pd.DataFrame):
            predicted = pd.DataFrame(predicted)
        if "close" not in predicted.columns:
            raise RuntimeError("Kronos predictor returned no close column")
        predicted = predicted.copy()
        if len(predicted) > inp.horizon:
            predicted = predicted.iloc[: inp.horizon]
        predicted.index = y_idx[: len(predicted)]

        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=predicted,
            latency_ms=latency_ms,
            meta={
                "model_id": self.model_id,
                "tokenizer_id": self.tokenizer_id,
                "size": self.size,
                "sample_count": self.sample_count,
                "max_context": self.max_context,
                "context_used": len(history),
                "device": self.device or "auto",
                "checkpoint": self.model_id,
            },
        )
