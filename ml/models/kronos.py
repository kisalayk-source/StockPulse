"""Kronos directional adapter scaffold (MVP-2).

Derives a directional probability from path forecasts; does not invent signals
from technical rules.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ml.models.base import ForecastModel


class KronosModel(ForecastModel):
    name = "kronos"
    version = "0.0"

    def train(self, dataset: pd.DataFrame) -> None:
        # Pretrained foundation weights; fine-tune path is out of MVP-1.
        _ = dataset

    def predict(self, features: pd.DataFrame | dict[str, float]) -> Any:
        raise NotImplementedError("KronosModel directional adapter lands in MVP-2")

    def predict_probability(self, features: pd.DataFrame | dict[str, float]) -> float:
        raise NotImplementedError("KronosModel directional adapter lands in MVP-2")
