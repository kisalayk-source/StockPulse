"""Abstract forecast model contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from forecasting.core.schema import ForecastInput, ForecastResult


class ForecastModel(ABC):
    """Every forecasting backend implements this interface."""

    name: str

    @abstractmethod
    def load(self) -> None:
        """Load weights/tokenizer. Called once, lazily, on first use."""

    @abstractmethod
    def predict(self, inp: ForecastInput) -> ForecastResult:
        """Return a ForecastResult regardless of the model's native output format."""

    @abstractmethod
    def supports(self, inp: ForecastInput) -> bool:
        """Return False so the registry can skip/fallback instead of crashing.

        Must not mutate ``inp`` (never silently truncate context).
        """
