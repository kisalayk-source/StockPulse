"""Spread, commission, exchange, and regulatory cost models.

When only OHLCV is available, bid/ask is synthesized as:

    spread = mid * spread.rate
    buy  = mid + spread / 2
    sell = mid - spread / 2

``mid`` defaults to the execution reference (next-bar open). This is an
assumption, not observed microstructure. If ``bid`` and ``ask`` columns are
present they are used instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from kronos_backtest.config import BacktestConfig, CostConfig, SpreadConfig
from kronos_backtest.types import Bar, Side


@dataclass(frozen=True)
class FillCosts:
    reference_price: float
    price_after_spread: float
    fill_price: float
    gross_value: float
    commission: float
    exchange_fees: float
    regulatory_fees: float
    spread_cost: float
    slippage_cost: float
    total_transaction_cost: float
    net_value: float

    def as_dict(self) -> dict[str, float]:
        return {
            "reference_price": self.reference_price,
            "price_after_spread": self.price_after_spread,
            "fill_price": self.fill_price,
            "gross_value": self.gross_value,
            "commission": self.commission,
            "exchange_fees": self.exchange_fees,
            "regulatory_fees": self.regulatory_fees,
            "spread_cost": self.spread_cost,
            "slippage_cost": self.slippage_cost,
            "total_transaction_cost": self.total_transaction_cost,
            "net_value": self.net_value,
        }


class SpreadModel:
    def quote(self, bar: Bar, side: Side, reference_price: float) -> tuple[float, float]:
        """Return (price_after_spread, spread_cost_per_share)."""
        raise NotImplementedError


@dataclass
class BidAskOrSyntheticSpread(SpreadModel):
    rate: float = 0.0005
    enabled: bool = True
    use_bid_ask_when_available: bool = True

    @classmethod
    def from_config(cls, config: SpreadConfig) -> "BidAskOrSyntheticSpread":
        return cls(
            rate=config.rate,
            enabled=config.enabled,
            use_bid_ask_when_available=config.use_bid_ask_when_available,
        )

    def quote(self, bar: Bar, side: Side, reference_price: float) -> tuple[float, float]:
        if not self.enabled:
            return reference_price, 0.0
        if (
            self.use_bid_ask_when_available
            and bar.bid is not None
            and bar.ask is not None
            and bar.ask >= bar.bid
        ):
            mid = (bar.bid + bar.ask) / 2.0
            quoted = bar.ask if side is Side.BUY else bar.bid
            return quoted, abs(quoted - mid)
        half = reference_price * self.rate / 2.0
        quoted = reference_price + half if side is Side.BUY else reference_price - half
        return quoted, abs(quoted - reference_price)


@dataclass
class TransactionCostModel:
    commission_rate: float = 0.0001
    exchange_fee_rate: float = 0.00005
    regulatory_fee_rate: float = 0.0
    spread_model: SpreadModel | None = None
    slippage_model: object | None = None

    @classmethod
    def from_config(cls, config: BacktestConfig) -> "TransactionCostModel":
        from kronos_backtest.slippage import ProportionalSlippage

        return cls(
            commission_rate=config.costs.commission_rate,
            exchange_fee_rate=config.costs.exchange_fee_rate,
            regulatory_fee_rate=config.costs.regulatory_fee_rate,
            spread_model=BidAskOrSyntheticSpread.from_config(config.spread),
            slippage_model=ProportionalSlippage.from_config(config.slippage),
        )

    @classmethod
    def from_cost_config(cls, config: CostConfig) -> "TransactionCostModel":
        return cls(
            commission_rate=config.commission_rate,
            exchange_fee_rate=config.exchange_fee_rate,
            regulatory_fee_rate=config.regulatory_fee_rate,
        )

    def calculate(self, side: Side, quantity: float, fill_price: float) -> dict[str, float]:
        """Fee/commission component given an already-determined fill price."""
        gross = abs(fill_price * quantity)
        commission = gross * self.commission_rate
        exchange = gross * self.exchange_fee_rate
        regulatory = gross * self.regulatory_fee_rate
        fees = commission + exchange + regulatory
        net = gross + fees if side is Side.BUY else gross - fees
        return {
            "gross_value": gross,
            "commission": commission,
            "exchange_fees": exchange,
            "regulatory_fees": regulatory,
            "net_value": net,
        }

    def price_and_costs(
        self,
        bar: Bar,
        side: Side,
        quantity: float,
        *,
        reference_price: float | None = None,
    ) -> FillCosts:
        """Strategy code must not call this to mutate the portfolio.

        The execution engine is the only consumer that turns costs into fills.
        """
        reference = bar.open if reference_price is None else reference_price
        spread_model = self.spread_model or BidAskOrSyntheticSpread(enabled=False)
        after_spread, spread_per_share = spread_model.quote(bar, side, reference)
        if self.slippage_model is None:
            fill_price, slip_per_share = after_spread, 0.0
        else:
            fill_price, slip_per_share = self.slippage_model.apply(after_spread, side)
        fees = self.calculate(side, quantity, fill_price)
        spread_cost = spread_per_share * quantity
        slippage_cost = slip_per_share * quantity
        total = (
            fees["commission"]
            + fees["exchange_fees"]
            + fees["regulatory_fees"]
            + spread_cost
            + slippage_cost
        )
        return FillCosts(
            reference_price=reference,
            price_after_spread=after_spread,
            fill_price=fill_price,
            gross_value=fees["gross_value"],
            commission=fees["commission"],
            exchange_fees=fees["exchange_fees"],
            regulatory_fees=fees["regulatory_fees"],
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            total_transaction_cost=total,
            net_value=fees["net_value"],
        )
