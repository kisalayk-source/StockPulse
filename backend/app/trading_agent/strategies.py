"""Trading mode strategy abstractions (options / day / long-term)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
        *,
        held_qty: float = 0.0,
    ) -> list[StrategyCandidate]:
        ...


def _position_qty(
    price: float,
    capital: float,
    risk_config: dict[str, Any],
    forecast: ForecastResult | None = None,
) -> float:
    if price <= 0 or capital <= 0:
        return 0.0
    max_pct = float(risk_config.get("max_position_size_pct") or 0.05)
    budget = capital * max_pct
    # Scale notional with path expected move when hybrid signal is actionable.
    strength = 1.0
    if forecast is not None:
        move = forecast.path_expected_return
        if move is None:
            move = forecast.expected_return
        try:
            move_f = abs(float(move or 0.0))
        except (TypeError, ValueError):
            move_f = 0.0
        # 0% move → 0.75x; ~4%+ move → up to 1.25x (still capped by max_pct budget).
        strength = max(0.75, min(1.25, 0.75 + move_f / 0.08))
        if forecast.signal_source == "unavailable":
            strength = 0.0
    qty = int((budget * strength) // price)
    # Never let strength > 1.0 exceed the max_position_size_pct notional budget.
    cap_qty = int(budget // price)
    if cap_qty > 0:
        qty = min(qty, cap_qty)
    return float(max(qty, 0))


def classify_empty_generate(
    *,
    forecast: ForecastResult,
    price: float,
    capital: float,
    risk_config: dict[str, Any],
    held_qty: float = 0.0,
) -> tuple[str, str]:
    """Explain why strategy engines produced no candidates for a symbol."""
    signal = str(forecast.signal or "").upper()
    if forecast.signal_source == "unavailable":
        return "unavailable", "Forecast signal unavailable"
    if signal not in {"BUY", "STRONG BUY", "SELL", "STRONG SELL"}:
        return "hold", f"Signal {signal or 'HOLD'} is not actionable"
    side = "buy" if "BUY" in signal else "sell"
    if side == "sell":
        held = float(held_qty or 0.0)
        if held <= 0 and not risk_config.get("short_selling_enabled", False):
            return "no_position", "Sell skipped; no long position and shorts disabled"
        if held > 0:
            return "no_candidate", "No strategy candidate for sell"
    qty = _position_qty(price, capital, risk_config, forecast)
    if qty <= 0:
        max_pct = float(risk_config.get("max_position_size_pct") or 0.05)
        budget = float(capital) * max_pct
        return "qty_zero", f"Position size 0 (budget {budget:.2f} vs price {price:.2f})"
    if not risk_config.get("allow_day_trading", True) and "BUY" not in signal:
        return "no_candidate", "Day trading disabled"
    return "no_candidate", "No strategy emitted a candidate"

def _path_levels(
    *,
    price: float,
    side: str,
    risk_config: dict[str, Any],
    forecast: ForecastResult,
    default_stop_pct: float,
    default_tp_pct: float,
) -> tuple[float, float]:
    """Prefer Kronos path target/stop when present; else risk-config percentages."""
    stop_pct = float(risk_config.get("default_stop_loss_pct") or default_stop_pct)
    tp_pct = float(risk_config.get("default_take_profit_pct") or default_tp_pct)

    path_stop = forecast.path_stop_price
    path_target = forecast.path_target_price
    path_ret = forecast.path_expected_return
    if path_ret is None:
        path_ret = forecast.expected_return

    if side == "buy":
        stop = price * (1 - stop_pct)
        take = price * (1 + tp_pct)
        if path_stop is not None and float(path_stop) < price:
            stop = float(path_stop)
        if path_target is not None and float(path_target) > price:
            take = float(path_target)
        elif path_ret is not None and float(path_ret) > 0:
            take = max(take, price * (1.0 + float(path_ret) * 0.85))
    else:
        stop = price * (1 + stop_pct)
        take = price * (1 - tp_pct)
        if path_stop is not None and float(path_stop) > price:
            stop = float(path_stop)
        if path_target is not None and float(path_target) < price:
            take = float(path_target)
        elif path_ret is not None and float(path_ret) < 0:
            take = min(take, price * (1.0 + float(path_ret) * 0.85))
    return stop, take


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_intraday_exit_candidates(
    *,
    symbol: str,
    quantity: float,
    mark_price: float,
    entry_price: float,
    stop_loss: float | None,
    take_profit: float | None,
    opened_at: datetime | None,
    risk_config: dict[str, Any],
    now: datetime | None = None,
    near_close: bool = False,
) -> list[StrategyCandidate]:
    """Close open longs when stop, take-profit, optional max-hold, or EOD triggers fire."""
    qty = float(quantity)
    if qty <= 0 or mark_price <= 0:
        return []

    current = _as_utc(now or datetime.now(timezone.utc))
    held_minutes = 0.0
    if opened_at is not None:
        held_minutes = (current - _as_utc(opened_at)).total_seconds() / 60.0

    # Protective stop/TP wait until the position has been held long enough (noise gate).
    min_exit = int(risk_config.get("min_exit_holding_minutes") or 0)
    allow_stop_tp = min_exit <= 0 or held_minutes >= min_exit

    reasons: list[str] = []
    if allow_stop_tp and stop_loss is not None and mark_price <= float(stop_loss):
        reasons.append("stop_loss")
    if allow_stop_tp and take_profit is not None and mark_price >= float(take_profit):
        reasons.append("take_profit")

    max_hold = int(risk_config.get("max_position_holding_minutes") or 0)
    if (
        bool(risk_config.get("max_holding_enabled"))
        and max_hold > 0
        and opened_at is not None
        and held_minutes >= max_hold
    ):
        reasons.append("max_holding")

    if near_close and risk_config.get("close_positions_before_market_close", False):
        reasons.append("eod_flatten")

    if not reasons:
        return []

    reason = reasons[0]
    return [
        StrategyCandidate(
            symbol=symbol.upper(),
            strategy="intraday_exit",
            trading_mode="day_trading",
            asset_type="equity",
            side="sell",
            quantity=qty,
            entry_price=mark_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            max_loss=abs(mark_price - float(entry_price)) * qty if entry_price else None,
            max_profit=None,
            metadata={
                "exit_reason": reason,
                "exit_reasons": reasons,
                "entry_price": entry_price,
                "opened_at": opened_at.isoformat() if opened_at else None,
                "held_minutes": held_minutes,
                "min_exit_holding_minutes": min_exit,
            },
        )
    ]


class DayTradingStrategy:
    name = "day_trading"

    def generate(
        self,
        symbol: str,
        forecast: ForecastResult,
        price: float,
        risk_config: dict[str, Any],
        capital: float,
        *,
        held_qty: float = 0.0,
    ) -> list[StrategyCandidate]:
        if not risk_config.get("allow_day_trading", True):
            return []
        if forecast.signal.upper() not in {"BUY", "STRONG BUY", "SELL", "STRONG SELL"}:
            return []
        if forecast.signal_source == "unavailable":
            return []
        side = "buy" if "BUY" in forecast.signal.upper() else "sell"
        if side == "sell":
            held = float(held_qty or 0.0)
            if held <= 0 and not risk_config.get("short_selling_enabled", False):
                return []
            qty = held if held > 0 else _position_qty(price, capital, risk_config, forecast)
        else:
            qty = _position_qty(price, capital, risk_config, forecast)
        if qty <= 0:
            return []
        stop, take = _path_levels(
            price=price,
            side=side,
            risk_config=risk_config,
            forecast=forecast,
            default_stop_pct=0.01,
            default_tp_pct=0.02,
        )
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
                metadata={
                    "max_holding_minutes": risk_config.get("max_position_holding_minutes"),
                    "signal_source": forecast.signal_source,
                    "path_expected_return": forecast.path_expected_return,
                },
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
        *,
        held_qty: float = 0.0,
    ) -> list[StrategyCandidate]:
        _ = held_qty
        if forecast.signal.upper() not in {"BUY", "STRONG BUY"}:
            return []
        if forecast.signal_source == "unavailable":
            return []
        qty = _position_qty(price, capital, risk_config, forecast)
        if qty <= 0:
            return []
        stop, take = _path_levels(
            price=price,
            side="buy",
            risk_config=risk_config,
            forecast=forecast,
            default_stop_pct=0.05,
            default_tp_pct=0.15,
        )
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
                    "signal_source": forecast.signal_source,
                    "path_expected_return": forecast.path_expected_return,
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
        *,
        held_qty: float = 0.0,
    ) -> list[StrategyCandidate]:
        _ = held_qty
        if not risk_config.get("allow_options", True):
            return []
        if forecast.signal_source == "unavailable":
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
