"""Model adapters (lazy imports so optional deps do not break package import)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forecasting.adapters.chronos_adapter import ChronosAdapter
    from forecasting.adapters.kronos_adapter import KronosAdapter
    from forecasting.adapters.lag_llama_adapter import LagLlamaAdapter
    from forecasting.adapters.timesfm_adapter import TimesFMAdapter

__all__ = [
    "ChronosAdapter",
    "KronosAdapter",
    "LagLlamaAdapter",
    "PersistenceAdapter",
    "TimesFMAdapter",
]


def __getattr__(name: str):
    if name == "KronosAdapter":
        from forecasting.adapters.kronos_adapter import KronosAdapter

        return KronosAdapter
    if name == "ChronosAdapter":
        from forecasting.adapters.chronos_adapter import ChronosAdapter

        return ChronosAdapter
    if name == "TimesFMAdapter":
        from forecasting.adapters.timesfm_adapter import TimesFMAdapter

        return TimesFMAdapter
    if name == "LagLlamaAdapter":
        from forecasting.adapters.lag_llama_adapter import LagLlamaAdapter

        return LagLlamaAdapter
    if name == "PersistenceAdapter":
        from forecasting.adapters.persistence_adapter import PersistenceAdapter

        return PersistenceAdapter
    raise AttributeError(name)
