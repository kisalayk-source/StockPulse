"""Deterministic risk engine for autonomous trade approval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.trading_agent.daily_loss import DailyLossService, DailyLossSnapshot
from app.trading_agent.risk_profiles import validate_risk_config

TradingModeKind = Literal["options", "day_trading", "long_term", "mixed"]


@dataclass
class ForecastResult:
    symbol: str
    signal: str
    confidence: float
    forecast_horizon: str
    expected_return: float
    downside_risk: float
    forecast_version: str
    generated_at: str
    features_snapshot_id: str
    model_name: str
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "signal": self.signal,
            "confidence": self.confidence,
            "forecast_horizon": self.forecast_horizon,
            "expected_return": self.expected_return,
            "downside_risk": self.downside_risk,
            "forecast_version": self.forecast_version,
            "generated_at": self.generated_at,
            "features_snapshot_id": self.features_snapshot_id,
            "model_name": self.model_name,
            "raw": self.raw,
        }


@dataclass
class TradeCandidateInput:
    symbol: str
    side: str  # buy | sell
    asset_type: str  # equity | option
    strategy: str
    quantity: float
    entry_price: float
    notional: float | None = None
    max_loss: float | None = None
    max_profit: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    sector: str | None = None
    industry: str | None = None
    trading_mode: TradingModeKind = "mixed"
    option_strategy: str | None = None
    days_to_expiration: int | None = None
    implied_volatility: float | None = None
    bid_ask_spread: float | None = None
    delta: float | None = None
    is_naked: bool = False
    market_open: bool = True
    forecast: ForecastResult | None = None
    idempotency_key: str | None = None


@dataclass
class PortfolioSnapshot:
    equity: float
    cash: float
    buying_power: float
    positions: list[dict[str, Any]] = field(default_factory=list)
    open_orders: list[dict[str, Any]] = field(default_factory=list)
    realized_pnl_today: float = 0.0
    unrealized_pnl: float = 0.0
    trading_fees_today: float = 0.0
    starting_daily_equity: float | None = None
    peak_equity: float | None = None
    trades_today: int = 0
    consecutive_losses: int = 0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    gross_exposure: float = 0.0

    def open_position_count(self) -> int:
        return len([p for p in self.positions if abs(float(p.get("quantity") or p.get("qty") or 0)) > 0])

    def sector_count(self, sector: str | None) -> int:
        if not sector:
            return 0
        return sum(
            1
            for p in self.positions
            if str(p.get("sector") or "").lower() == sector.lower()
            and abs(float(p.get("quantity") or p.get("qty") or 0)) > 0
        )

    def industry_count(self, industry: str | None) -> int:
        if not industry:
            return 0
        return sum(
            1
            for p in self.positions
            if str(p.get("industry") or "").lower() == industry.lower()
            and abs(float(p.get("quantity") or p.get("qty") or 0)) > 0
        )

    def has_open_order(self, symbol: str, side: str) -> bool:
        ticker = symbol.upper()
        for order in self.open_orders:
            if str(order.get("symbol") or "").upper() != ticker:
                continue
            if str(order.get("side") or "").lower() == side.lower():
                status = str(order.get("status") or "").lower()
                if status in {"pending", "accepted", "new", "partially_filled", "open"}:
                    return True
        return False

    def position_qty(self, symbol: str) -> float:
        ticker = symbol.upper()
        total = 0.0
        for p in self.positions:
            if str(p.get("symbol") or "").upper() == ticker:
                total += float(p.get("quantity") or p.get("qty") or 0)
        return total


@dataclass
class RiskDecision:
    approved: bool
    reason: str
    position_size: float
    max_loss: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward_ratio: float | None = None
    warnings: list[str] = field(default_factory=list)
    daily_loss: DailyLossSnapshot | None = None
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "reason": self.reason,
            "position_size": self.position_size,
            "max_loss": self.max_loss,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward_ratio": self.risk_reward_ratio,
            "warnings": self.warnings,
            "daily_loss": self.daily_loss.to_dict() if self.daily_loss else None,
            "checks": self.checks,
        }


class RiskEngine:
    """Deterministic trade gate — no LLM involvement."""

    def __init__(self, daily_loss_service: DailyLossService | None = None) -> None:
        self.daily_loss = daily_loss_service or DailyLossService()

    def evaluate(
        self,
        trade_candidate: TradeCandidateInput,
        portfolio: PortfolioSnapshot,
        risk_config: dict[str, Any],
        *,
        agent_status: str = "paper",
        live_trading_enabled: bool = False,
    ) -> RiskDecision:
        errors = validate_risk_config(risk_config)
        if errors:
            return RiskDecision(
                approved=False,
                reason=f"Invalid risk configuration: {errors[0]}",
                position_size=0.0,
                checks={"config_errors": errors},
            )

        warnings: list[str] = []
        checks: dict[str, Any] = {}
        quantity = float(trade_candidate.quantity)
        entry = float(trade_candidate.entry_price)
        notional = float(trade_candidate.notional) if trade_candidate.notional is not None else quantity * entry
        if trade_candidate.asset_type == "option":
            notional = quantity * entry * 100.0

        starting_equity = portfolio.starting_daily_equity or portfolio.equity
        daily = self.daily_loss.evaluate(
            starting_equity=starting_equity,
            current_equity=portfolio.equity,
            realized_pnl=portfolio.realized_pnl_today,
            unrealized_pnl=portfolio.unrealized_pnl,
            trading_fees=portfolio.trading_fees_today,
            risk_config=risk_config,
        )
        checks["daily_loss"] = daily.to_dict()

        def reject(reason: str, **extra: Any) -> RiskDecision:
            checks.update(extra)
            return RiskDecision(
                approved=False,
                reason=reason,
                position_size=0.0,
                max_loss=trade_candidate.max_loss,
                stop_loss=trade_candidate.stop_loss,
                take_profit=trade_candidate.take_profit,
                warnings=warnings,
                daily_loss=daily,
                checks=checks,
            )

        if agent_status in {"disabled", "emergency_stop"}:
            return reject(f"Agent status '{agent_status}' blocks new orders")
        if agent_status == "paused":
            return reject("Agent is paused")
        if agent_status == "live" and not live_trading_enabled:
            return reject("Live trading is not explicitly enabled")

        # Max daily loss — applies to all trading modes
        if daily.limit_reached and trade_candidate.side.lower() == "buy":
            return reject(
                "Max daily loss limit reached",
                daily_loss_blocked=True,
                trading_mode=trade_candidate.trading_mode,
            )

        # Forecast confidence / expected return
        forecast = trade_candidate.forecast
        if forecast:
            min_conf = float(risk_config.get("min_forecast_confidence") or 0)
            if forecast.confidence < min_conf:
                return reject(
                    f"Forecast confidence {forecast.confidence:.2f} below minimum {min_conf:.2f}"
                )
            min_ret = float(risk_config.get("min_expected_return") or 0)
            if forecast.expected_return < min_ret and trade_candidate.side.lower() == "buy":
                return reject(
                    f"Expected return {forecast.expected_return:.4f} below minimum {min_ret:.4f}"
                )
            signal = forecast.signal.upper()
            if trade_candidate.side.lower() == "buy" and signal in {"SELL", "STRONG SELL"}:
                return reject(f"Forecast signal {signal} conflicts with buy")
            if trade_candidate.side.lower() == "sell" and signal in {"BUY", "STRONG BUY"}:
                warnings.append(f"Sell against bullish forecast {signal}")

        # Market hours for day trading
        if trade_candidate.trading_mode == "day_trading" and not trade_candidate.market_open:
            return reject("Market is closed; day trades cannot be submitted")

        if trade_candidate.trading_mode == "day_trading" and not risk_config.get("allow_day_trading", True):
            return reject("Day trading is disabled by risk configuration")

        max_trades = int(risk_config.get("max_trades_per_day") or 0)
        if (
            trade_candidate.trading_mode == "day_trading"
            and max_trades > 0
            and portfolio.trades_today >= max_trades
        ):
            return reject(f"Maximum day trades per day ({max_trades}) reached")

        # Drawdown
        peak = portfolio.peak_equity or starting_equity
        if peak > 0:
            drawdown = 1.0 - (portfolio.equity / peak)
            max_dd = float(risk_config.get("max_portfolio_drawdown") or 1.0)
            checks["drawdown"] = drawdown
            if drawdown >= max_dd:
                return reject(f"Portfolio drawdown {drawdown:.1%} exceeds {max_dd:.1%} limit")

        # Weekly / monthly loss
        if starting_equity > 0:
            weekly_loss_pct = max(0.0, -portfolio.weekly_pnl / starting_equity)
            monthly_loss_pct = max(0.0, -portfolio.monthly_pnl / starting_equity)
            max_weekly = float(risk_config.get("max_weekly_loss_percent") or 100) / 100.0
            max_monthly = float(risk_config.get("max_monthly_loss_percent") or 100) / 100.0
            checks["weekly_loss_pct"] = weekly_loss_pct
            checks["monthly_loss_pct"] = monthly_loss_pct
            if weekly_loss_pct >= max_weekly and trade_candidate.side.lower() == "buy":
                return reject(f"Weekly loss {weekly_loss_pct:.1%} exceeds {max_weekly:.1%} limit")
            if monthly_loss_pct >= max_monthly and trade_candidate.side.lower() == "buy":
                return reject(f"Monthly loss {monthly_loss_pct:.1%} exceeds {max_monthly:.1%} limit")

        # Open positions
        max_open = int(risk_config.get("max_open_positions") or 100)
        if trade_candidate.side.lower() == "buy" and portfolio.open_position_count() >= max_open:
            if portfolio.position_qty(trade_candidate.symbol) <= 0:
                return reject(f"Maximum open positions ({max_open}) reached")

        # Sector / industry concentration
        max_sector = int(risk_config.get("max_positions_per_sector") or 100)
        if trade_candidate.sector and portfolio.sector_count(trade_candidate.sector) >= max_sector:
            if portfolio.position_qty(trade_candidate.symbol) <= 0:
                return reject(f"Sector concentration limit ({max_sector}) reached for {trade_candidate.sector}")

        max_industry = int(risk_config.get("max_positions_per_industry") or 100)
        if trade_candidate.industry and portfolio.industry_count(trade_candidate.industry) >= max_industry:
            if portfolio.position_qty(trade_candidate.symbol) <= 0:
                return reject(
                    f"Industry concentration limit ({max_industry}) reached for {trade_candidate.industry}"
                )

        # Buying power / order value
        if trade_candidate.side.lower() == "buy" and notional > portfolio.buying_power:
            return reject(
                f"Order notional {notional:.2f} exceeds buying power {portfolio.buying_power:.2f}"
            )
        max_order_value = float(risk_config.get("max_order_value") or 0)
        if max_order_value > 0 and notional > max_order_value:
            return reject(f"Order value {notional:.2f} exceeds max order value {max_order_value:.2f}")
        max_qty = float(risk_config.get("max_order_quantity") or 0)
        if max_qty > 0 and quantity > max_qty:
            return reject(f"Order quantity {quantity} exceeds max {max_qty}")

        # Position size
        equity = portfolio.equity or 0.0
        if equity > 0 and trade_candidate.side.lower() == "buy":
            position_pct = notional / equity
            max_pos_pct = float(risk_config.get("max_position_size_pct") or 1.0)
            checks["position_pct"] = position_pct
            if position_pct > max_pos_pct + 1e-9:
                return reject(
                    f"Position size {position_pct:.1%} exceeds max {max_pos_pct:.1%}"
                )
            max_pos_amt = risk_config.get("max_position_size_amount")
            if max_pos_amt is not None and notional > float(max_pos_amt):
                return reject(f"Position notional {notional:.2f} exceeds max ${float(max_pos_amt):.2f}")

            exposure = (portfolio.gross_exposure + notional) / equity
            max_exposure = float(risk_config.get("max_portfolio_exposure") or 1.0)
            checks["portfolio_exposure"] = exposure
            if exposure > max_exposure + 1e-9:
                return reject(
                    f"Portfolio exposure {exposure:.1%} exceeds max {max_exposure:.1%}"
                )

            # Risk per trade
            stop = trade_candidate.stop_loss
            risk_amount = trade_candidate.max_loss
            if risk_amount is None and stop is not None and entry > 0:
                risk_amount = abs(entry - stop) * quantity * (100.0 if trade_candidate.asset_type == "option" else 1.0)
            if risk_amount is not None:
                risk_pct = risk_amount / equity
                max_risk_pct = float(risk_config.get("max_risk_per_trade_pct") or 1.0)
                checks["risk_per_trade_pct"] = risk_pct
                if risk_pct > max_risk_pct + 1e-9:
                    return reject(
                        f"Risk per trade {risk_pct:.2%} exceeds max {max_risk_pct:.2%}"
                    )
                max_risk_amt = risk_config.get("max_risk_per_trade_amount")
                if max_risk_amt is not None and risk_amount > float(max_risk_amt):
                    return reject(
                        f"Risk per trade ${risk_amount:.2f} exceeds max ${float(max_risk_amt):.2f}"
                    )

        # Short selling
        if (
            trade_candidate.side.lower() == "sell"
            and trade_candidate.asset_type == "equity"
            and not risk_config.get("short_selling_enabled", False)
        ):
            held = portfolio.position_qty(trade_candidate.symbol)
            if quantity > max(held, 0.0):
                return reject("Short selling is disabled")

        # Options-specific
        if trade_candidate.asset_type == "option" or trade_candidate.trading_mode == "options":
            if not risk_config.get("allow_options", True):
                return reject("Options trading is disabled")
            if trade_candidate.is_naked and not risk_config.get("allow_naked_options", False):
                return reject("Naked options are disabled")
            if risk_config.get("defined_risk_options_only") and trade_candidate.is_naked:
                return reject("Only defined-risk options strategies are allowed")
            allowed = risk_config.get("allowed_option_strategies") or []
            strategy_name = trade_candidate.option_strategy or trade_candidate.strategy
            if allowed and strategy_name not in allowed:
                return reject(f"Options strategy '{strategy_name}' is not allowed")
            max_premium = float(risk_config.get("max_premium_per_trade") or 0)
            if max_premium > 0 and notional > max_premium:
                return reject(f"Options premium {notional:.2f} exceeds max {max_premium:.2f}")
            max_opt_loss = float(risk_config.get("max_loss_per_options_position") or 0)
            if max_opt_loss > 0 and trade_candidate.max_loss is not None and trade_candidate.max_loss > max_opt_loss:
                return reject(
                    f"Options max loss {trade_candidate.max_loss:.2f} exceeds {max_opt_loss:.2f}"
                )
            dte = trade_candidate.days_to_expiration
            if dte is not None:
                min_dte = int(risk_config.get("min_days_to_expiration") or 0)
                max_dte = int(risk_config.get("max_days_to_expiration") or 10_000)
                if dte < min_dte or dte > max_dte:
                    return reject(f"Days to expiration {dte} outside [{min_dte}, {max_dte}]")
            iv = trade_candidate.implied_volatility
            max_iv = float(risk_config.get("max_implied_volatility") or 0)
            if iv is not None and max_iv > 0 and iv > max_iv:
                return reject(f"Implied volatility {iv:.2f} exceeds max {max_iv:.2f}")
            spread = trade_candidate.bid_ask_spread
            max_spread = float(risk_config.get("max_bid_ask_spread") or 0)
            if spread is not None and max_spread > 0 and spread > max_spread:
                return reject(f"Bid/ask spread {spread:.3f} exceeds max {max_spread:.3f}")

        # Duplicate orders
        if portfolio.has_open_order(trade_candidate.symbol, trade_candidate.side):
            return reject("Duplicate open order exists for symbol/side")

        # Consecutive losses pause
        if risk_config.get("pause_after_consecutive_losses"):
            max_consec = int(risk_config.get("max_consecutive_losses") or 0)
            if max_consec > 0 and portfolio.consecutive_losses >= max_consec:
                return reject(f"Paused after {portfolio.consecutive_losses} consecutive losses")

        # Size / stops
        stop_loss = trade_candidate.stop_loss
        take_profit = trade_candidate.take_profit
        if stop_loss is None and entry > 0 and trade_candidate.side.lower() == "buy":
            stop_pct = float(risk_config.get("default_stop_loss_pct") or 0)
            if stop_pct > 0:
                stop_loss = entry * (1.0 - stop_pct)
        if take_profit is None and entry > 0 and trade_candidate.side.lower() == "buy":
            tp_pct = float(risk_config.get("default_take_profit_pct") or 0)
            if tp_pct > 0:
                take_profit = entry * (1.0 + tp_pct)

        max_loss = trade_candidate.max_loss
        if max_loss is None and stop_loss is not None:
            max_loss = abs(entry - stop_loss) * quantity * (100.0 if trade_candidate.asset_type == "option" else 1.0)

        max_profit = trade_candidate.max_profit
        if max_profit is None and take_profit is not None:
            max_profit = abs(take_profit - entry) * quantity * (100.0 if trade_candidate.asset_type == "option" else 1.0)

        rr = None
        if max_loss and max_loss > 0 and max_profit is not None:
            rr = max_profit / max_loss
            min_rr = float(risk_config.get("min_risk_reward_ratio") or 0)
            if min_rr > 0 and rr < min_rr:
                return reject(f"Risk/reward {rr:.2f} below minimum {min_rr:.2f}")

        if daily.status in {"warning", "critical"}:
            warnings.extend(daily.warnings)

        return RiskDecision(
            approved=True,
            reason="approved",
            position_size=quantity,
            max_loss=max_loss,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=rr,
            warnings=warnings,
            daily_loss=daily,
            checks=checks,
        )
