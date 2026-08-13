"""Replaceable slippage models."""

from __future__ import annotations

from dataclasses import dataclass

from kronos_backtest.config import SlippageConfig
from kronos_backtest.types import Side


class SlippageModel:
    """Apply a signed slippage adjustment to a reference price."""

    def apply(self, price: float, side: Side) -> tuple[float, float]:
        """Return (adjusted_price, slippage_cost_per_share)."""
        raise NotImplementedError


@dataclass
class ProportionalSlippage(SlippageModel):
    rate: float = 0.0005
    enabled: bool = True

    @classmethod
    def from_config(cls, config: SlippageConfig) -> "ProportionalSlippage":
        return cls(rate=config.rate, enabled=config.enabled)

    def apply(self, price: float, side: Side) -> tuple[float, float]:
        if not self.enabled or self.rate == 0:
            return price, 0.0
        if side is Side.BUY:
            filled = price * (1.0 + self.rate)
        else:
            filled = price * (1.0 - self.rate)
        return filled, abs(filled - price)


class ZeroSlippage(SlippageModel):
    def apply(self, price: float, side: Side) -> tuple[float, float]:
        return price, 0.0
