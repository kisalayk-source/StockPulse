"""Directional predictive model interface.

Separate from ``forecasting.core.base.ForecastModel`` (path adapters).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class ForecastModel(ABC):
    """Plugin contract for directional probability models."""

    name: str
    version: str = "1.0"

    @abstractmethod
    def train(self, dataset: pd.DataFrame) -> None:
        """Train on a frame with feature columns plus ``target``."""

    @abstractmethod
    def predict(self, features: pd.DataFrame | dict[str, float]) -> Any:
        """Return class labels or raw scores."""

    @abstractmethod
    def predict_probability(self, features: pd.DataFrame | dict[str, float]) -> float:
        """Return P(positive class) in [0, 1] for a single row or frame mean."""

    def supports(self, features: pd.DataFrame | dict[str, float]) -> bool:
        return True
