"""LightGBM adapter scaffold (MVP-2)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ml.models.base import ForecastModel


class LightGBMModel(ForecastModel):
    name = "lightgbm"
    version = "0.0"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = dict(params or {})
        self._model = None

    def train(self, dataset: pd.DataFrame) -> None:
        raise NotImplementedError("LightGBMModel lands in MVP-2")

    def predict(self, features: pd.DataFrame | dict[str, float]) -> Any:
        raise NotImplementedError("LightGBMModel lands in MVP-2")

    def predict_probability(self, features: pd.DataFrame | dict[str, float]) -> float:
        raise NotImplementedError("LightGBMModel lands in MVP-2")
