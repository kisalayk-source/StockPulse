"""Trading mode strategy abstractions (options / day / long-term)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.trading_agent.risk_engine import ForecastResult, TradeCandidateInput


@dataclass
class StrategyCandidate:
    symbol: str
    strategy: str
    trading_mode: str
    asset_type: str
    side: str
    quantity: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    max_loss: float | None = None
    max_profit: float | None = None
    option_strategy: str | None = None
    days_to_expiration: int | None = None
    implied_volatility: float | None = None
    bid_ask_spread: float | None = None
    delta: float | None = None
    is_naked: bool = False
    metadata: dict[str, Any] | None = None

    def to_trade_input(
        self,
        *,
        forecast: ForecastResult | None,
        market_open: bool,
        sector: str | None = None,
        industry: str | None = None,
        idempotency_key: str | None = None,
    ) -> TradeCandidateInput:
        return TradeCandidateInput(
            symbol=self.symbol,
            side=self.side,
            asset_type=self.asset_type,
            strategy=self.strategy,
            quantity=self.quantity,
            entry_price=self.entry_price,
            max_loss=self.max_loss,
            max_profit=self.max_profit,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            sector=sector,
            industry=industry,
            trading_mode=self.trading_mode,  # type: ignore[arg-type]
            option_strategy=self.option_strategy,
            days_to_expiration=self.days_to_expiration,
            implied_volatility=self.implied_volatility,
            bid_ask_spread=self.bid_ask_spread,
            delta=self.delta,
            is_naked=self.is_naked,
            market_open=market_open,
            forecast=forecast,
            idempotency_key=idempotency_key,
        )


class StrategyEngine(Protocol):
    name: str

    def generate(
        self,
        symbol: str,
        forecast: ForecastResult,
        price: float,
        risk_config: dict[str, Any],
        capital: float,
    ) -> list[StrategyCandidate]:
        ...


def _position_qty(price: float, capital: float, risk_config: dict[str, Any]) -> float:
    if price <= 0 or capital <= 0:
        return 0.0
    max_pct = float(risk_config.get("max_position_size_pct") or 0.05)
    budget = capital * max_pct
    qty = int(budget // price)
    return float(max(qty, 0))


class DayTradingStrategy:
    name = "day_trading"

    def generate(
        self,
        symbol: str,
        forecast: ForecastResult,
        price: float,
        risk_config: dict[str, Any],
        capital: float,
    ) -> list[StrategyCandidate]:
        if not risk_config.get("allow_day_trading", True):
            return []
        if forecast.signal.upper() not in {"BUY", "STRONG BUY", "SELL", "STRONG SELL"}:
            return []
        qty = _position_qty(price, capital, risk_config)
        if qty <= 0:
            return []
        side = "buy" if "BUY" in forecast.signal.upper() else "sell"
        stop_pct = float(risk_config.get("default_stop_loss_pct") or 0.01)
        tp_pct = float(risk_config.get("default_take_profit_pct") or 0.02)
        stop = price * (1 - stop_pct) if side == "buy" else price * (1 + stop_pct)
        take = price * (1 + tp_pct) if side == "buy" else price * (1 - tp_pct)
        return [
            StrategyCandidate(
                symbol=symbol.upper(),
                strategy="intraday_momentum",
                trading_mode="day_trading",
                asset_type="equity",
                side=side,
                quantity=qty,
                entry_price=price,
                stop_loss=stop,
                take_profit=take,
                max_loss=abs(price - stop) * qty,
                max_profit=abs(take - price) * qty,
                metadata={"max_holding_minutes": risk_config.get("max_position_holding_minutes")},
            )
        ]


class LongTermStrategy:
    name = "long_term"

    def generate(
        self,
        symbol: str,
        forecast: ForecastResult,
        price: float,
        risk_config: dict[str, Any],
        capital: float,
    ) -> list[StrategyCandidate]:
        if forecast.signal.upper() not in {"BUY", "STRONG BUY"}:
            return []
        qty = _position_qty(price, capital, risk_config)
        if qty <= 0:
            return []
        stop_pct = float(risk_config.get("default_stop_loss_pct") or 0.05)
        tp_pct = float(risk_config.get("default_take_profit_pct") or 0.15)
        stop = price * (1 - stop_pct)
        take = price * (1 + tp_pct)
        return [
            StrategyCandidate(
                symbol=symbol.upper(),
                strategy="buy_and_hold",
                trading_mode="long_term",
                asset_type="equity",
                side="buy",
                quantity=qty,
                entry_price=price,
                stop_loss=stop,
                take_profit=take,
                max_loss=abs(price - stop) * qty,
                max_profit=abs(take - price) * qty,
                metadata={
                    "min_holding_period_days": risk_config.get("min_holding_period_days"),
                    "close_eod": False,
                },
            )
        ]


class OptionsStrategy:
    """Defined-risk options strategies only by default — never naked sells."""

    name = "options"

    def generate(
        self,
        symbol: str,
        forecast: ForecastResult,
        price: float,
        risk_config: dict[str, Any],
        capital: float,
    ) -> list[StrategyCandidate]:
        if not risk_config.get("allow_options", True):
            return []
        allowed = set(risk_config.get("allowed_option_strategies") or [])
        signal = forecast.signal.upper()
        out: list[StrategyCandidate] = []
        premium = max(price * 0.03, 1.0)
        max_premium = float(risk_config.get("max_premium_per_trade") or 500)
        contracts = max(1, int(max_premium // (premium * 100)))
        contracts = min(contracts, int(float(risk_config.get("max_order_quantity") or 10)))

        if "BUY" in signal and "long_call" in allowed:
            out.append(
                StrategyCandidate(
                    symbol=symbol.upper(),
                    strategy="long_call",
                    trading_mode="options",
                    asset_type="option",
                    side="buy",
                    quantity=float(contracts),
                    entry_price=premium,
                    max_loss=premium * 100 * contracts,
                    max_profit=None,
                    option_strategy="long_call",
                    days_to_expiration=30,
                    implied_volatility=0.35,
                    bid_ask_spread=0.05,
                    delta=0.45,
                    is_naked=False,
                    metadata={"strike": round(price * 1.05, 2), "right": "call"},
                )
            )
        if "SELL" in signal and "long_put" in allowed:
            out.append(
                StrategyCandidate(
                    symbol=symbol.upper(),
                    strategy="long_put",
                    trading_mode="options",
                    asset_type="option",
                    side="buy",
                    quantity=float(contracts),
                    entry_price=premium,
                    max_loss=premium * 100 * contracts,
                    max_profit=None,
                    option_strategy="long_put",
                    days_to_expiration=30,
                    implied_volatility=0.35,
                    bid_ask_spread=0.05,
                    delta=-0.45,
                    is_naked=False,
                    metadata={"strike": round(price * 0.95, 2), "right": "put"},
                )
            )
        if "BUY" in signal and "bull_call_spread" in allowed:
            width = max(price * 0.05, 1.0)
            debit = premium * 0.6
            out.append(
                StrategyCandidate(
                    symbol=symbol.upper(),
                    strategy="bull_call_spread",
                    trading_mode="options",
                    asset_type="option",
                    side="buy",
                    quantity=float(contracts),
                    entry_price=debit,
                    max_loss=debit * 100 * contracts,
                    max_profit=(width - debit) * 100 * contracts,
                    option_strategy="bull_call_spread",
                    days_to_expiration=35,
                    implied_volatility=0.30,
                    bid_ask_spread=0.08,
                    delta=0.30,
                    is_naked=False,
                    metadata={"long_strike": round(price, 2), "short_strike": round(price + width, 2)},
                )
            )
        return out


def strategies_for_mode(trading_type: str) -> list[StrategyEngine]:
    mode = (trading_type or "mixed").lower()
    if mode == "options":
        return [OptionsStrategy()]
    if mode == "day_trading":
        return [DayTradingStrategy()]
    if mode == "long_term":
        return [LongTermStrategy()]
    return [OptionsStrategy(), DayTradingStrategy(), LongTermStrategy()]
