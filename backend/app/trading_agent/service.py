"""Autonomous Trading Agent service — lifecycle, decisions, paper execution."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from time import sleep
from typing import Any, Callable, TypeVar
from uuid import uuid4

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.trading_agent.broker import (
    AlpacaBrokerAdapter,
    BrokerAdapter,
    OrderRequest,
    PaperBrokerAdapter,
)
from app.trading_agent.daily_loss import DailyLossService, trading_date_for
from app.trading_agent.forecast_provider import ForecastProvider, KronosForecastProvider
from app.trading_agent.models import (
    AgentConfig,
    AgentEvent,
    AgentOrder,
    AgentPosition,
    AgentRun,
    DailyLossRecord,
    TradeCandidate,
    TradePlan,
)
from app.trading_agent.risk_engine import PortfolioSnapshot, RiskEngine
from app.trading_agent.risk_profiles import get_risk_config, merge_risk_config, validate_risk_config
from app.trading_agent.strategies import StrategyCandidate, build_intraday_exit_candidates, strategies_for_mode


ACTIVE_STATUSES = {"paper", "live", "paused", "configured"}
T = TypeVar("T")


def _retry_locked(fn: Callable[[], T], *, attempts: int = 8, delay: float = 0.15) -> T:
    """Retry SQLite 'database is locked' contention from concurrent writers."""
    last: Exception | None = None
    for index in range(attempts):
        try:
            return fn()
        except OperationalError as exc:
            last = exc
            if "locked" not in str(exc).lower() or index == attempts - 1:
                raise
            sleep(delay * (index + 1))
    assert last is not None
    raise last


class TradingAgentService:
    def __init__(
        self,
        *,
        forecast_provider: ForecastProvider | None = None,
        risk_engine: RiskEngine | None = None,
        daily_loss_service: DailyLossService | None = None,
        alpaca: Any | None = None,
        paper_brokers: dict[int, PaperBrokerAdapter] | None = None,
        settings: Any | None = None,
    ) -> None:
        self.forecast_provider = forecast_provider
        self.risk_engine = risk_engine or RiskEngine()
        self.daily_loss = daily_loss_service or DailyLossService()
        self.alpaca = alpaca
        self.settings = settings
        self._paper_brokers = paper_brokers if paper_brokers is not None else {}

    def _assert_live_allowed(self) -> None:
        if self.settings is not None and not bool(getattr(self.settings, "allow_live_trading", False)):
            raise ValueError("Live trading is disabled on this server")

    # ── persistence helpers ──────────────────────────────────────────

    def get_or_create_config(self, session: Session, user_id: int) -> AgentConfig:
        def _load() -> AgentConfig:
            row = (
                session.query(AgentConfig)
                .filter(AgentConfig.user_id == user_id)
                .order_by(AgentConfig.id.asc())
                .first()
            )
            if row:
                return row
            profile = "medium"
            risk = get_risk_config(profile)
            created = AgentConfig(
                user_id=user_id,
                name="Default Agent",
                enabled=False,
                status="disabled",
                mode="paper",
                trading_type="mixed",
                risk_profile=profile,
                risk_config=risk,
                capital_allocation=float(risk.get("capital_allocation") or 10_000),
                forecast_enabled=True,
                live_trading_enabled=False,
                universe=["SPY", "AAPL", "MSFT", "NVDA", "AMZN"],
                cycle_interval_seconds=300,
            )
            session.add(created)
            session.flush()
            self._record_event(session, created, "AGENT_CREATED", "Agent configuration created", "info")
            return created

        return _retry_locked(_load)

    def resolved_risk_config(self, config: AgentConfig) -> dict[str, Any]:
        base = get_risk_config(config.risk_profile)
        return merge_risk_config(base, config.risk_config or {})

    def update_config(self, session: Session, config: AgentConfig, payload: dict[str, Any]) -> AgentConfig:
        if "name" in payload and payload["name"]:
            config.name = str(payload["name"])
        if "trading_type" in payload and payload["trading_type"]:
            config.trading_type = str(payload["trading_type"])
        if "capital_allocation" in payload and payload["capital_allocation"] is not None:
            config.capital_allocation = float(payload["capital_allocation"])
        if "forecast_enabled" in payload and payload["forecast_enabled"] is not None:
            config.forecast_enabled = bool(payload["forecast_enabled"])
        if "universe" in payload and payload["universe"] is not None:
            config.universe = [str(s).upper() for s in payload["universe"]]
        if "cycle_interval_seconds" in payload and payload["cycle_interval_seconds"] is not None:
            interval = int(payload["cycle_interval_seconds"])
            if interval < 60 or interval > 86_400:
                raise ValueError("cycle_interval_seconds must be between 60 and 86400")
            config.cycle_interval_seconds = interval

        profile = payload.get("risk_profile") or config.risk_profile
        overrides = dict(config.risk_config or {})
        if payload.get("risk_config"):
            overrides.update(payload["risk_config"])
        if payload.get("capital_allocation") is not None:
            overrides["capital_allocation"] = float(payload["capital_allocation"])

        # Live enablement requires explicit confirmation and server allow flag
        if payload.get("live_trading_enabled") is True:
            self._assert_live_allowed()
            confirmation = str(payload.get("live_confirmation") or "")
            if confirmation.upper() != "LIVE":
                raise ValueError("Live trading requires confirmation phrase LIVE")
            config.live_trading_enabled = True
            config.live_confirmation_at = datetime.now(timezone.utc)
            self._record_event(session, config, "LIVE_ENABLED", "Live trading explicitly enabled", "warning")
        elif payload.get("live_trading_enabled") is False:
            config.live_trading_enabled = False
            if config.status == "live":
                config.status = "paused"
                config.mode = "paper"
            self._record_event(session, config, "LIVE_DISABLED", "Live trading disabled", "info")

        merged = get_risk_config(profile, overrides if profile == "custom" or payload.get("risk_config") else None)
        if profile != "custom" and not payload.get("risk_config"):
            merged = get_risk_config(profile)
            # Preserve daily-loss customizations across profile switches when provided
            for key in (
                "max_daily_loss_enabled",
                "max_daily_loss_amount",
                "max_daily_loss_percent",
                "daily_loss_calculation",
                "daily_loss_reset_time",
                "daily_loss_timezone",
                "daily_loss_action",
                "capital_allocation",
            ):
                if key in overrides:
                    merged[key] = overrides[key]
        elif payload.get("risk_config"):
            merged = get_risk_config(profile, overrides)

        errors = validate_risk_config(merged)
        if errors:
            raise ValueError(errors[0])

        config.risk_profile = profile
        config.risk_config = merged
        if config.status == "disabled":
            config.status = "configured"
        config.updated_at = datetime.now(timezone.utc)
        session.flush()
        return config

    def update_daily_loss(self, session: Session, config: AgentConfig, payload: dict[str, Any]) -> AgentConfig:
        risk = dict(self.resolved_risk_config(config))
        for key, value in payload.items():
            if value is not None:
                risk[key] = value
        errors = validate_risk_config(risk)
        if errors:
            raise ValueError(errors[0])
        config.risk_config = risk
        if config.risk_profile != "custom":
            # Editing daily loss fields keeps profile label but stores overrides
            pass
        config.updated_at = datetime.now(timezone.utc)
        session.flush()
        self._record_event(session, config, "DAILY_LOSS_CONFIG_UPDATED", "Max daily loss settings updated", "info")
        return config

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self, session: Session, config: AgentConfig, *, mode: str = "paper", live_confirmation: str | None = None) -> AgentConfig:
        if mode == "live":
            self._assert_live_allowed()
            if not config.live_trading_enabled:
                raise ValueError("Enable live trading in settings before starting in live mode")
            if str(live_confirmation or "").upper() != "LIVE":
                raise ValueError("Live start requires confirmation phrase LIVE")
            config.mode = "live"
            config.status = "live"
        else:
            config.mode = "paper"
            config.status = "paper"
        config.enabled = True
        config.last_cycle_at = None
        config.updated_at = datetime.now(timezone.utc)
        run = AgentRun(agent_config_id=config.id, status="running", forecast_version="forecast-mode")
        session.add(run)
        session.flush()
        self._record_event(
            session,
            config,
            "AGENT_STARTED",
            f"Agent started in {config.mode} mode",
            "info",
            {"run_id": run.id},
        )
        # Ensure daily loss record exists without resetting on restart
        self.ensure_daily_loss_record(session, config, reset=False)
        return config

    def pause(self, session: Session, config: AgentConfig) -> AgentConfig:
        if config.status not in {"paper", "live"}:
            raise ValueError(f"Cannot pause from status {config.status}")
        config.status = "paused"
        config.updated_at = datetime.now(timezone.utc)
        self._record_event(session, config, "AGENT_PAUSED", "Agent paused", "warning")
        return config

    def resume(self, session: Session, config: AgentConfig) -> AgentConfig:
        if config.status != "paused":
            raise ValueError("Agent is not paused")
        # Explicit resume required after daily-loss block
        risk = self.resolved_risk_config(config)
        snapshot = self.get_daily_loss_snapshot(session, config)
        if snapshot.get("limit_reached"):
            raise ValueError("Max daily loss still reached; reset daily loss or wait for next reset before resuming")
        config.status = "live" if config.mode == "live" and config.live_trading_enabled else "paper"
        if config.status == "paper":
            config.mode = "paper"
        config.last_cycle_at = None
        config.updated_at = datetime.now(timezone.utc)
        self._record_event(session, config, "AGENT_RESUMED", f"Agent resumed in {config.status} mode", "info")
        _ = risk
        return config

    def emergency_stop(self, session: Session, config: AgentConfig, *, cancel_orders: bool = True) -> AgentConfig:
        config.status = "emergency_stop"
        config.enabled = False
        config.updated_at = datetime.now(timezone.utc)
        if cancel_orders:
            broker = self._broker_for(config, session=session)
            for order in broker.get_open_orders():
                oid = str(order.get("id") or order.get("broker_order_id") or "")
                if oid:
                    try:
                        broker.cancel_order(oid)
                    except Exception:
                        pass
        self._record_event(
            session,
            config,
            "EMERGENCY_STOP",
            "Emergency stop engaged; new orders blocked; open orders canceled when supported",
            "critical",
        )
        return config

    # ── daily loss ───────────────────────────────────────────────────

    def ensure_daily_loss_record(
        self,
        session: Session,
        config: AgentConfig,
        *,
        reset: bool = False,
        now: datetime | None = None,
    ) -> DailyLossRecord:
        now = now or datetime.now(timezone.utc)
        risk = self.resolved_risk_config(config)
        tz = str(risk.get("daily_loss_timezone") or "America/Los_Angeles")
        reset_hhmm = str(risk.get("daily_loss_reset_time") or "00:00")
        trading_day = trading_date_for(now, tz, reset_hhmm)
        broker = self._broker_for(config, session=session)
        account = broker.get_account()
        existing = (
            session.query(DailyLossRecord)
            .filter(
                DailyLossRecord.agent_config_id == config.id,
                DailyLossRecord.trading_date == trading_day,
                DailyLossRecord.timezone == tz,
            )
            .one_or_none()
        )
        if existing and not reset:
            return existing

        if isinstance(broker, PaperBrokerAdapter):
            broker.mark_day_start()

        if existing and reset:
            # Explicit user reset only — archive by updating values for a fresh window
            existing.starting_equity = account.equity
            existing.current_equity = account.equity
            existing.realized_pnl = 0.0
            existing.unrealized_pnl = 0.0
            existing.trading_fees = 0.0
            existing.daily_loss = 0.0
            existing.daily_loss_percent = 0.0
            existing.status = "active"
            existing.trades_blocked = 0
            existing.reset_at = now
            existing.max_daily_loss_amount = risk.get("max_daily_loss_amount")
            existing.max_daily_loss_percent = risk.get("max_daily_loss_percent")
            session.flush()
            self._record_event(session, config, "DAILY_LOSS_RESET", "Daily loss explicitly reset by user", "warning")
            return existing

        # New calendar window (natural reset) — preserve historical rows for prior dates
        row = DailyLossRecord(
            agent_config_id=config.id,
            trading_date=trading_day,
            timezone=tz,
            starting_equity=account.equity,
            current_equity=account.equity,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            trading_fees=0.0,
            daily_loss=0.0,
            daily_loss_percent=0.0,
            max_daily_loss_amount=risk.get("max_daily_loss_amount"),
            max_daily_loss_percent=risk.get("max_daily_loss_percent"),
            status="active",
            reset_at=now,
        )
        session.add(row)
        session.flush()
        return row

    def refresh_daily_loss(self, session: Session, config: AgentConfig) -> dict[str, Any]:
        record = self.ensure_daily_loss_record(session, config, reset=False)
        broker = self._broker_for(config, session=session)
        account = broker.get_account()
        positions = broker.get_positions()
        unrealized = sum(p.unrealized_pnl for p in positions)
        if isinstance(broker, PaperBrokerAdapter):
            realized = broker.today_realized_pnl()
        else:
            realized = float(account.raw.get("today_realized_pnl") or account.raw.get("realized_pnl") or record.realized_pnl)
        fees = float(account.raw.get("fees") or record.trading_fees)
        risk = self.resolved_risk_config(config)
        snapshot = self.daily_loss.evaluate(
            starting_equity=record.starting_equity,
            current_equity=account.equity,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            trading_fees=fees,
            risk_config=risk,
            last_reset_at=record.reset_at,
        )
        record.current_equity = account.equity
        record.realized_pnl = realized
        record.unrealized_pnl = unrealized
        record.trading_fees = fees
        record.daily_loss = snapshot.daily_loss
        record.daily_loss_percent = snapshot.daily_loss_percent
        record.status = snapshot.status
        record.max_daily_loss_amount = snapshot.max_daily_loss_amount
        record.max_daily_loss_percent = snapshot.max_daily_loss_percent
        session.flush()

        if snapshot.limit_reached and config.status in {"paper", "live"}:
            self._enforce_daily_loss_action(session, config, risk)
        return snapshot.to_dict()

    def get_daily_loss_snapshot(self, session: Session, config: AgentConfig) -> dict[str, Any]:
        return self.refresh_daily_loss(session, config)

    def reset_daily_loss(self, session: Session, config: AgentConfig) -> dict[str, Any]:
        self.ensure_daily_loss_record(session, config, reset=True)
        return self.refresh_daily_loss(session, config)

    def _enforce_daily_loss_action(self, session: Session, config: AgentConfig, risk: dict[str, Any]) -> None:
        action = str(risk.get("daily_loss_action") or "cancel_orders_and_pause")
        self._record_event(
            session,
            config,
            "MAX_DAILY_LOSS_REACHED",
            f"Max daily loss reached; action={action}",
            "critical",
            {"action": action},
        )
        broker = self._broker_for(config, session=session)
        if action in {"cancel_open_orders", "cancel_orders_and_pause", "emergency_stop"}:
            for order in broker.get_open_orders():
                oid = str(order.get("id") or order.get("broker_order_id") or "")
                if oid:
                    try:
                        broker.cancel_order(oid)
                    except Exception:
                        pass
        if action == "emergency_stop":
            config.status = "emergency_stop"
            config.enabled = False
        elif action in {"pause_agent", "cancel_orders_and_pause"}:
            config.status = "paused"
        config.updated_at = datetime.now(timezone.utc)
        session.flush()

    # ── decision cycle ───────────────────────────────────────────────


    @staticmethod
    def _session_day_start_utc(risk: dict[str, Any], *, now: datetime | None = None) -> datetime:
        tz_name = str(risk.get("daily_loss_timezone") or "America/Los_Angeles")
        reset = str(risk.get("daily_loss_reset_time") or "00:00")
        current = now or datetime.now(timezone.utc)
        day = trading_date_for(current, tz_name, reset)
        hour_s, minute_s = reset.split(":", 1)
        start_local = datetime.combine(day, time(hour=int(hour_s), minute=int(minute_s)), tzinfo=ZoneInfo(tz_name))
        return start_local.astimezone(timezone.utc)

    @staticmethod
    def _near_equity_close(now: datetime, *, minutes_before: int = 15) -> bool:
        eastern = now.astimezone(ZoneInfo("America/New_York"))
        close = eastern.replace(hour=16, minute=0, second=0, microsecond=0)
        window_start = close - timedelta(minutes=max(minutes_before, 0))
        return window_start <= eastern <= close + timedelta(minutes=5)

    def _open_plan_levels(self, session: Session, config: AgentConfig, symbol: str) -> tuple[float | None, float | None, float | None]:
        """Return (entry, stop_loss, take_profit) from the latest approved/executed plan."""
        plan = (
            session.query(TradePlan)
            .join(TradeCandidate)
            .join(AgentRun)
            .filter(
                AgentRun.agent_config_id == config.id,
                TradeCandidate.symbol == symbol.upper(),
                TradePlan.status.in_(("approved", "executed")),
            )
            .order_by(TradePlan.id.desc())
            .first()
        )
        if plan is None:
            return None, None, None
        return plan.entry_price, plan.stop_loss, plan.take_profit

    def _position_opened_at(self, session: Session, config: AgentConfig, symbol: str) -> datetime | None:
        """Return when the current open lot started (latest buy fill), not first-ever row create time."""
        row = (
            session.query(AgentPosition)
            .filter(
                AgentPosition.agent_config_id == config.id,
                AgentPosition.symbol == symbol.upper(),
                AgentPosition.quantity != 0,
            )
            .order_by(AgentPosition.id.desc())
            .first()
        )
        if row is None:
            return None
        latest_buy = (
            session.query(AgentOrder)
            .join(TradePlan)
            .join(TradeCandidate)
            .join(AgentRun)
            .filter(
                AgentRun.agent_config_id == config.id,
                AgentOrder.symbol == symbol.upper(),
                AgentOrder.side == "buy",
                AgentOrder.status == "filled",
            )
            .order_by(AgentOrder.filled_at.desc(), AgentOrder.id.desc())
            .first()
        )
        if latest_buy is not None and latest_buy.filled_at is not None:
            return latest_buy.filled_at
        return row.opened_at

    def _process_candidate(
        self,
        session: Session,
        config: AgentConfig,
        run: AgentRun,
        broker: BrokerAdapter,
        portfolio: PortfolioSnapshot,
        risk: dict[str, Any],
        candidate: StrategyCandidate,
        forecast,
        *,
        market_open: bool,
        execute: bool,
        approved: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
    ) -> PortfolioSnapshot:
        trade_input = candidate.to_trade_input(
            forecast=forecast,
            market_open=market_open,
            idempotency_key=f"{run.id}-{candidate.symbol}-{candidate.strategy}-{uuid4().hex[:8]}",
        )
        decision = self.risk_engine.evaluate(
            trade_input,
            portfolio,
            risk,
            agent_status=config.status,
            live_trading_enabled=config.live_trading_enabled,
        )
        forecast_snapshot = forecast.to_dict() if forecast is not None and hasattr(forecast, "to_dict") else {
            "symbol": candidate.symbol,
            "signal": "EXIT",
            "confidence": 1.0,
        }
        tc = TradeCandidate(
            agent_run_id=run.id,
            symbol=candidate.symbol.upper(),
            asset_type=candidate.asset_type,
            strategy=candidate.strategy,
            forecast_snapshot=forecast_snapshot,
            risk_decision=decision.to_dict(),
            status="approved" if decision.approved else "rejected",
        )
        session.add(tc)
        _retry_locked(session.flush)

        if not decision.approved:
            rejected.append({"symbol": candidate.symbol, "strategy": candidate.strategy, "reason": decision.reason})
            if decision.checks.get("daily_loss_blocked"):
                record = (
                    session.query(DailyLossRecord)
                    .filter(DailyLossRecord.agent_config_id == config.id)
                    .order_by(DailyLossRecord.id.desc())
                    .first()
                )
                if record:
                    record.trades_blocked = int(record.trades_blocked or 0) + 1
                self._record_event(
                    session,
                    config,
                    "TRADE_BLOCKED_DAILY_LOSS",
                    f"Blocked {candidate.symbol} {candidate.strategy}: {decision.reason}",
                    "warning",
                )
            return portfolio

        plan = TradePlan(
            trade_candidate_id=tc.id,
            entry_price=candidate.entry_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            position_size=decision.position_size,
            max_loss=decision.max_loss,
            max_profit=candidate.max_profit,
            risk_reward_ratio=decision.risk_reward_ratio,
            status="approved",
            plan_payload={
                "symbol": candidate.symbol.upper(),
                "mode": candidate.trading_mode,
                "strategy": candidate.strategy,
                "forecast_signal": getattr(forecast, "signal", "EXIT") if forecast is not None else "EXIT",
                "forecast_confidence": getattr(forecast, "confidence", 1.0) if forecast is not None else 1.0,
                "entry_price": candidate.entry_price,
                "stop_loss": decision.stop_loss,
                "take_profit": decision.take_profit,
                "max_loss": decision.max_loss,
                "max_profit": candidate.max_profit,
                "risk_reward_ratio": decision.risk_reward_ratio,
                "position_size": decision.position_size,
                "status": "approved",
                "metadata": candidate.metadata or {},
            },
        )
        session.add(plan)
        _retry_locked(session.flush)

        order_payload = None
        if execute:
            order_payload = self._submit_plan(
                session, config, plan, candidate, trade_input.idempotency_key or uuid4().hex
            )
            portfolio = self._portfolio_snapshot(session, config, broker)

        approved.append(
            {
                "symbol": candidate.symbol,
                "strategy": candidate.strategy,
                "plan_id": plan.id,
                "order": order_payload,
                "metadata": candidate.metadata or {},
            }
        )
        return portfolio

    def run_cycle(
        self,
        session: Session,
        config: AgentConfig,
        *,
        symbols: list[str] | None = None,
        execute: bool = True,
        market_open: bool = True,
        prices: dict[str, float] | None = None,
        now: datetime | None = None,
        near_close: bool | None = None,
    ) -> dict[str, Any]:
        if config.status not in {"paper", "live"}:
            raise ValueError(f"Agent must be running to cycle (status={config.status})")
        if not config.forecast_enabled:
            raise ValueError("Forecast Mode must be enabled for the trading agent")
        if self.forecast_provider is None:
            raise ValueError("Forecast provider is not configured")

        risk = self.resolved_risk_config(config)
        tickers = [s.upper() for s in (symbols or config.universe or ["SPY"])]
        run = AgentRun(
            agent_config_id=config.id,
            status="running",
            forecast_version="forecast-mode",
            summary={"symbols": tickers},
        )
        session.add(run)
        _retry_locked(session.flush)

        broker = self._broker_for(config, session=session)
        if prices:
            if isinstance(broker, PaperBrokerAdapter):
                for sym, px in prices.items():
                    broker.set_price(sym, px)

        daily = self.refresh_daily_loss(session, config)
        self._sync_positions(session, config, broker)
        portfolio = self._portfolio_snapshot(session, config, broker)
        approved: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        clock = now or datetime.now(timezone.utc)
        close_flag = self._near_equity_close(clock) if near_close is None else bool(near_close)

        # Exits first: stop / take-profit / max hold / EOD flatten for open equity longs.
        open_positions = [
            p for p in broker.get_positions()
            if float(getattr(p, "quantity", 0) or 0) > 0 and str(getattr(p, "asset_type", "equity")).lower() in {"equity", "stock", ""}
        ]
        for pos in open_positions:
            symbol = str(pos.symbol).upper()
            mark = float(getattr(pos, "current_price", 0) or 0)
            if mark <= 0 and isinstance(broker, PaperBrokerAdapter):
                mark = float(broker.prices.get(symbol) or (prices or {}).get(symbol) or 0)
            if mark <= 0 and prices and symbol in prices:
                mark = float(prices[symbol])
            if mark <= 0:
                continue
            entry, stop, take = self._open_plan_levels(session, config, symbol)
            entry_price = float(entry or getattr(pos, "average_entry_price", 0) or mark)
            if stop is None and entry_price > 0:
                stop_pct = float(risk.get("default_stop_loss_pct") or 0)
                stop = entry_price * (1 - stop_pct) if stop_pct > 0 else None
            if take is None and entry_price > 0:
                tp_pct = float(risk.get("default_take_profit_pct") or 0)
                take = entry_price * (1 + tp_pct) if tp_pct > 0 else None
            opened_at = self._position_opened_at(session, config, symbol)
            for candidate in build_intraday_exit_candidates(
                symbol=symbol,
                quantity=float(pos.quantity),
                mark_price=mark,
                entry_price=entry_price,
                stop_loss=stop,
                take_profit=take,
                opened_at=opened_at,
                risk_config=risk,
                now=clock,
                near_close=close_flag,
            ):
                portfolio = self._process_candidate(
                    session,
                    config,
                    run,
                    broker,
                    portfolio,
                    risk,
                    candidate,
                    forecast=None,
                    market_open=market_open,
                    execute=execute,
                    approved=approved,
                    rejected=rejected,
                )

        for symbol in tickers:
            try:
                forecast = self.forecast_provider.get_forecast(symbol, "1Day")
            except Exception as exc:
                self._record_event(
                    session,
                    config,
                    "FORECAST_ERROR",
                    f"Forecast failed for {symbol}: {exc}",
                    "warning",
                )
                continue
            price = (prices or {}).get(symbol.upper())
            if price is None:
                if isinstance(broker, PaperBrokerAdapter) and symbol.upper() in broker.prices:
                    price = broker.prices[symbol.upper()]
                elif self.alpaca is not None:
                    try:
                        snap = self.alpaca.snapshot(symbol)
                        price = float(snap.get("current_price") or 0)
                    except Exception:
                        price = 0.0
                else:
                    price = 100.0
            if not price and isinstance(broker, PaperBrokerAdapter):
                # Paper fallback mark so cycles remain testable without live market data
                price = 100.0
                broker.set_price(symbol, price)
            if not price:
                continue

            held_qty = float(portfolio.position_qty(symbol))
            for engine in strategies_for_mode(config.trading_type):
                # Filter mixed mode by trading_type preference already handled
                if config.trading_type != "mixed" and engine.name != config.trading_type:
                    continue
                for candidate in engine.generate(
                    symbol,
                    forecast,
                    float(price),
                    risk,
                    float(config.capital_allocation),
                    held_qty=held_qty,
                ):
                    # Avoid opening a new buy when we already flat-exited this symbol in this cycle.
                    if candidate.side.lower() == "buy" and any(
                        a.get("symbol") == symbol and a.get("strategy") == "intraday_exit" for a in approved
                    ):
                        continue
                    portfolio = self._process_candidate(
                        session,
                        config,
                        run,
                        broker,
                        portfolio,
                        risk,
                        candidate,
                        forecast=forecast,
                        market_open=market_open,
                        execute=execute,
                        approved=approved,
                        rejected=rejected,
                    )
                    held_qty = float(portfolio.position_qty(symbol))

        run.status = "completed"
        run.ended_at = datetime.now(timezone.utc)
        run.summary = {
            "symbols": tickers,
            "approved": len(approved),
            "rejected": len(rejected),
            "daily_loss": daily,
        }
        config.last_cycle_at = run.ended_at
        config.updated_at = run.ended_at
        auto_adjust = self._maybe_auto_adjust_risk(
            session,
            config,
            approved=approved,
            rejected=rejected,
            market_open=market_open,
        )
        if auto_adjust:
            run.summary["auto_adjust"] = auto_adjust
        _retry_locked(session.flush)
        self._sync_positions(session, config, broker)
        return {
            "run_id": run.id,
            "approved": approved,
            "rejected": rejected,
            "auto_adjust": auto_adjust,
            "daily_loss": self.refresh_daily_loss(session, config),
            "performance": self.performance(session, config),
        }


    def _submit_plan(
        self,
        session: Session,
        config: AgentConfig,
        plan: TradePlan,
        candidate: Any,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if config.status == "live" and not config.live_trading_enabled:
            raise ValueError("Live trading is not enabled")
        if config.mode == "live" and not config.live_trading_enabled:
            raise ValueError("Live trading is not enabled")

        broker = self._broker_for(config, session=session)
        # Prevent duplicate by idempotency key
        existing = session.query(AgentOrder).filter(AgentOrder.idempotency_key == idempotency_key).one_or_none()
        if existing:
            return {
                "id": existing.id,
                "broker_order_id": existing.broker_order_id,
                "status": existing.status,
                "duplicate": True,
            }

        order_req = OrderRequest(
            symbol=candidate.symbol,
            side=candidate.side,
            quantity=float(plan.position_size),
            order_type="market",
            asset_type=candidate.asset_type,
            idempotency_key=idempotency_key,
            mode=config.mode,
        )
        result = broker.submit_order(order_req)
        now = datetime.now(timezone.utc)
        row = AgentOrder(
            trade_plan_id=plan.id,
            broker_order_id=result.broker_order_id,
            idempotency_key=idempotency_key,
            status=result.status,
            submitted_at=now,
            filled_at=now if result.status == "filled" else None,
            filled_quantity=result.filled_quantity,
            average_fill_price=result.average_fill_price,
            side=candidate.side,
            order_type="market",
            requested_quantity=float(plan.position_size),
            symbol=candidate.symbol.upper(),
            error_message=result.error_message,
        )
        session.add(row)
        if result.status == "filled":
            plan.status = "executed"
        elif result.status == "rejected":
            plan.status = "rejected"
            # Do not create a filled position on rejection
        session.flush()
        self._record_event(
            session,
            config,
            "ORDER_SUBMITTED" if result.status != "rejected" else "ORDER_REJECTED",
            f"{candidate.symbol} {candidate.side} → {result.status}",
            "info" if result.status != "rejected" else "warning",
            result.to_dict(),
        )
        return {"id": row.id, **result.to_dict()}

    # ── queries ──────────────────────────────────────────────────────

    def config_payload(self, session: Session, config: AgentConfig) -> dict[str, Any]:
        daily = self.get_daily_loss_snapshot(session, config)
        return {
            "id": config.id,
            "name": config.name,
            "enabled": config.enabled,
            "status": config.status,
            "mode": config.mode,
            "trading_type": config.trading_type,
            "risk_profile": config.risk_profile,
            "risk_config": self.resolved_risk_config(config),
            "capital_allocation": config.capital_allocation,
            "forecast_enabled": config.forecast_enabled,
            "live_trading_enabled": config.live_trading_enabled,
            "universe": config.universe or [],
            "cycle_interval_seconds": int(config.cycle_interval_seconds or 300),
            "last_cycle_at": config.last_cycle_at.isoformat() if config.last_cycle_at else None,
            "daily_loss": daily,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    def list_candidates(self, session: Session, config: AgentConfig, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            session.query(TradeCandidate)
            .join(AgentRun)
            .filter(AgentRun.agent_config_id == config.id)
            .order_by(TradeCandidate.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "asset_type": r.asset_type,
                "strategy": r.strategy,
                "status": r.status,
                "forecast_snapshot": r.forecast_snapshot,
                "risk_decision": r.risk_decision,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def list_trade_plans(self, session: Session, config: AgentConfig, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            session.query(TradePlan)
            .join(TradeCandidate)
            .join(AgentRun)
            .filter(AgentRun.agent_config_id == config.id)
            .order_by(TradePlan.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "status": r.status,
                "entry_price": r.entry_price,
                "stop_loss": r.stop_loss,
                "take_profit": r.take_profit,
                "position_size": r.position_size,
                "max_loss": r.max_loss,
                "max_profit": r.max_profit,
                "risk_reward_ratio": r.risk_reward_ratio,
                "plan": r.plan_payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def list_orders(self, session: Session, config: AgentConfig, limit: int = 200) -> list[dict[str, Any]]:
        rows = (
            session.query(AgentOrder)
            .join(TradePlan)
            .join(TradeCandidate)
            .join(AgentRun)
            .filter(AgentRun.agent_config_id == config.id)
            .order_by(AgentOrder.id.desc())
            .limit(limit)
            .all()
        )
        payload = [
            {
                "id": r.id,
                "broker_order_id": r.broker_order_id,
                "status": r.status,
                "symbol": r.symbol,
                "side": r.side,
                "filled_quantity": r.filled_quantity,
                "average_fill_price": r.average_fill_price,
                "requested_quantity": r.requested_quantity,
                "error_message": r.error_message,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "filled_at": r.filled_at.isoformat() if r.filled_at else None,
            }
            for r in rows
        ]
        # Prefer filled orders first so Performance trade count aligns with visible history.
        payload.sort(key=lambda o: (0 if o["status"] == "filled" else 1, -int(o["id"])))
        return payload

    def list_positions(self, session: Session, config: AgentConfig) -> list[dict[str, Any]]:
        self._sync_positions(session, config, self._broker_for(config, session=session))
        rows = (
            session.query(AgentPosition)
            .filter(AgentPosition.user_id == config.user_id, AgentPosition.quantity != 0)
            .all()
        )
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "asset_type": r.asset_type,
                "quantity": r.quantity,
                "average_entry_price": r.average_entry_price,
                "current_price": r.current_price,
                "unrealized_pnl": r.unrealized_pnl,
                "realized_pnl": r.realized_pnl,
            }
            for r in rows
        ]

    def list_events(self, session: Session, config: AgentConfig, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            session.query(AgentEvent)
            .filter(AgentEvent.agent_config_id == config.id)
            .order_by(AgentEvent.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "message": r.message,
                "severity": r.severity,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def list_forecasts(self, session: Session, config: AgentConfig) -> list[dict[str, Any]]:
        _ = session
        if self.forecast_provider is None:
            return []
        out = []
        for symbol in config.universe or []:
            try:
                out.append(self.forecast_provider.get_forecast(symbol, "1Day").to_dict())
            except Exception as exc:
                out.append({"symbol": symbol, "error": str(exc)})
        return out

    @staticmethod
    def _asset_multiplier(asset_type: str | None) -> float:
        return 100.0 if str(asset_type or "").lower() == "option" else 1.0

    def performance(self, session: Session, config: AgentConfig) -> dict[str, Any]:
        orders = self.list_orders(session, config, limit=500)
        filled = [o for o in orders if o["status"] == "filled"]
        broker = self._broker_for(config, session=session)
        # Persist any flat realized rows before reading.
        self._sync_positions(session, config, broker)
        all_rows = (
            session.query(AgentPosition)
            .filter(AgentPosition.agent_config_id == config.id)
            .all()
        )
        open_rows = [r for r in all_rows if abs(float(r.quantity or 0)) > 1e-9]
        realized = sum(float(r.realized_pnl or 0) for r in all_rows)
        if isinstance(broker, PaperBrokerAdapter):
            # Prefer live paper ledger when it is ahead of DB (same process, pre-commit edge).
            broker_realized = float(broker.realized_pnl)
            if abs(broker_realized) >= abs(realized) - 1e-9:
                realized = broker_realized
        unrealized = sum(float(r.unrealized_pnl or 0) for r in open_rows)
        # Capital still tied up in open longs (cost basis), not mark-to-market P/L.
        capital_invested = sum(
            abs(float(r.quantity or 0))
            * float(r.average_entry_price or 0)
            * self._asset_multiplier(r.asset_type)
            for r in open_rows
        )
        market_value_open = sum(
            abs(float(r.quantity or 0))
            * float(r.current_price or r.average_entry_price or 0)
            * self._asset_multiplier(r.asset_type)
            for r in open_rows
        )
        # Lifetime cash returned from exits (sell fill notional), distinct from realized P/L.
        proceeds_from_exits = 0.0
        for order in filled:
            if str(order.get("side") or "").lower() != "sell":
                continue
            qty = float(order.get("filled_quantity") or 0)
            px = float(order.get("average_fill_price") or 0)
            if qty > 0 and px > 0:
                proceeds_from_exits += qty * px
        account = broker.get_account()
        if isinstance(broker, PaperBrokerAdapter):
            starting_capital = float(broker.starting_cash)
        else:
            starting_capital = float(config.capital_allocation or 0)
        account_equity = float(account.equity)
        equity_change = account_equity - starting_capital
        events = (
            session.query(AgentEvent)
            .filter(
                AgentEvent.agent_config_id == config.id,
                AgentEvent.event_type.in_(["MAX_DAILY_LOSS_REACHED", "TRADE_BLOCKED_DAILY_LOSS"]),
            )
            .all()
        )
        blocked = sum(1 for e in events if e.event_type == "TRADE_BLOCKED_DAILY_LOSS")
        hit = sum(1 for e in events if e.event_type == "MAX_DAILY_LOSS_REACHED")
        wins = [o for o in filled if (o.get("average_fill_price") or 0) > 0]
        return {
            "total_pnl": realized + unrealized,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "capital_invested": capital_invested,
            "market_value_open": market_value_open,
            "proceeds_from_exits": proceeds_from_exits,
            "starting_capital": starting_capital,
            "account_equity": account_equity,
            "equity_change": equity_change,
            "number_of_trades": len(filled),
            "win_rate": None,
            "average_win": None,
            "average_loss": None,
            "profit_factor": None,
            "max_drawdown": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_daily_loss_reached_count": hit,
            "trades_blocked_by_daily_loss": blocked,
            "positions_open": len(open_rows),
            "orders_filled": len(filled),
            "note": (
                "total_pnl is profit/loss (realized + unrealized). "
                "capital_invested is open cost basis; proceeds_from_exits is lifetime sell notional. "
                "Forecast vs execution performance remain separate via forecast_snapshot on candidates."
            ),
            "sample_filled": len(wins),
        }

    # ── internals ────────────────────────────────────────────────────

    def _broker_for(self, config: AgentConfig, session: Session | None = None) -> BrokerAdapter:
        # Prefer the user's Alpaca account for both paper and live so agent fills
        # and cash/equity match the real broker ledger (not a local $25k simulator).
        if self.alpaca is not None:
            mode = (
                "live"
                if config.mode == "live" and config.live_trading_enabled
                else "paper"
            )
            return AlpacaBrokerAdapter(self.alpaca, mode=mode)
        if config.id not in self._paper_brokers:
            risk = self.resolved_risk_config(config)
            starting = float(risk.get("starting_capital") or config.capital_allocation or 25_000)
            broker = PaperBrokerAdapter(starting_cash=starting)
            self._paper_brokers[config.id] = broker
            if session is not None:
                self._hydrate_paper_broker(session, config, broker)
        return self._paper_brokers[config.id]

    def _hydrate_paper_broker(
        self, session: Session, config: AgentConfig, broker: PaperBrokerAdapter
    ) -> None:
        rows = (
            session.query(AgentPosition)
            .filter(AgentPosition.agent_config_id == config.id)
            .all()
        )
        total_realized = 0.0
        open_cost = 0.0
        for row in rows:
            realized = float(row.realized_pnl or 0)
            total_realized += realized
            qty = float(row.quantity or 0)
            if abs(qty) <= 1e-9 and abs(realized) <= 1e-9:
                continue
            entry = float(row.average_entry_price or 0)
            asset_type = str(row.asset_type or "equity")
            broker.restore_position(
                symbol=row.symbol,
                quantity=qty,
                average_entry_price=entry,
                current_price=float(row.current_price or 0) or None,
                realized_pnl=realized,
                asset_type=asset_type,
            )
            if abs(qty) > 1e-9:
                open_cost += abs(qty) * entry * self._asset_multiplier(asset_type)
        # Reconstruct cash after restart: buys reduce cash, sells return proceeds.
        # Equivalently cash = starting - open_cost + realized.
        broker.cash = float(broker.starting_cash) - open_cost + total_realized
        broker.realized_pnl = total_realized
        broker.day_start_realized = total_realized

    def _maybe_auto_adjust_risk(
        self,
        session: Session,
        config: AgentConfig,
        *,
        approved: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
        market_open: bool,
    ) -> dict[str, Any] | None:
        """Loosen thresholds one step when a cycle rejects all entry opportunities."""
        entry_rejected = [
            r
            for r in rejected
            if str(r.get("strategy") or "") != "intraday_exit"
        ]
        entry_approved = [
            a
            for a in approved
            if str(a.get("strategy") or "") != "intraday_exit"
        ]
        if entry_approved or not entry_rejected:
            return None

        reasons = [str(r.get("reason") or "") for r in entry_rejected]
        if reasons and all("market is closed" in reason.lower() for reason in reasons):
            return None
        if not market_open and all("market is closed" in reason.lower() for reason in reasons):
            return None

        risk = self.resolved_risk_config(config)
        tz_name = str(risk.get("daily_loss_timezone") or "America/Los_Angeles")
        reset_hhmm = str(risk.get("daily_loss_reset_time") or "00:00")
        today = trading_date_for(datetime.now(timezone.utc), tz_name, reset_hhmm).isoformat()
        overrides = dict(config.risk_config or {})
        prior_date = str(overrides.get("auto_adjust_date") or "")
        count = int(overrides.get("auto_adjust_count") or 0) if prior_date == today else 0
        if count >= 3:
            self._record_event(
                session,
                config,
                "RISK_AUTO_ADJUST_SKIPPED",
                f"Skipped auto-adjust: already loosened risk {count} times today after "
                f"{len(entry_rejected)} rejected opportunities.",
                "info",
                {"rejected": len(entry_rejected), "count": count},
            )
            return None

        from collections import Counter

        top_reason = Counter(reasons).most_common(1)[0][0] if reasons else "unknown"
        changes: list[str] = []

        old_conf = float(risk.get("min_forecast_confidence") or 0.55)
        new_conf = max(0.40, round(old_conf - 0.05, 2))
        if new_conf < old_conf - 1e-9:
            overrides["min_forecast_confidence"] = new_conf
            changes.append(f"min forecast confidence {old_conf:.2f} → {new_conf:.2f}")

        old_ret = float(risk.get("min_expected_return") or 0.005)
        new_ret = max(0.001, round(old_ret - 0.002, 4))
        if new_ret < old_ret - 1e-9:
            overrides["min_expected_return"] = new_ret
            changes.append(f"min expected return {old_ret:.4f} → {new_ret:.4f}")

        if any("max open positions" in reason.lower() for reason in reasons):
            old_open = int(risk.get("max_open_positions") or 10)
            new_open = min(15, old_open + 1)
            if new_open > old_open:
                overrides["max_open_positions"] = new_open
                changes.append(f"max open positions {old_open} → {new_open}")

        if not changes:
            return None

        overrides["auto_adjust_date"] = today
        overrides["auto_adjust_count"] = count + 1
        config.risk_config = overrides
        config.risk_profile = "custom"
        config.updated_at = datetime.now(timezone.utc)
        message = (
            f"Loosened {'; '.join(changes)} because all {len(entry_rejected)} "
            f"opportunities were rejected (top reason: {top_reason})."
        )
        self._record_event(
            session,
            config,
            "RISK_AUTO_ADJUSTED",
            message,
            "warning",
            {
                "changes": changes,
                "rejected_count": len(entry_rejected),
                "top_reason": top_reason,
                "auto_adjust_count": count + 1,
            },
        )
        return {"message": message, "changes": changes, "rejected_count": len(entry_rejected)}

    def _portfolio_snapshot(
        self, session: Session, config: AgentConfig, broker: BrokerAdapter
    ) -> PortfolioSnapshot:
        account = broker.get_account()
        positions = broker.get_positions()
        record = (
            session.query(DailyLossRecord)
            .filter(
                DailyLossRecord.agent_config_id == config.id,
                DailyLossRecord.trading_date == trading_date_for(
                    datetime.now(timezone.utc),
                    str(self.resolved_risk_config(config).get("daily_loss_timezone") or "America/Los_Angeles"),
                    str(self.resolved_risk_config(config).get("daily_loss_reset_time") or "00:00"),
                ),
            )
            .order_by(DailyLossRecord.id.desc())
            .first()
        )
        starting = record.starting_equity if record else account.equity
        if isinstance(broker, PaperBrokerAdapter):
            today_realized = broker.today_realized_pnl()
        else:
            today_realized = float(account.raw.get("today_realized_pnl") or account.raw.get("realized_pnl") or (record.realized_pnl if record else 0))
        return PortfolioSnapshot(
            equity=account.equity,
            cash=account.cash,
            buying_power=account.buying_power,
            positions=[
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "qty": p.quantity,
                    "market_value": p.market_value,
                    "sector": None,
                    "industry": None,
                }
                for p in positions
            ],
            open_orders=broker.get_open_orders(),
            realized_pnl_today=today_realized,
            unrealized_pnl=sum(p.unrealized_pnl for p in positions),
            trading_fees_today=float(account.raw.get("fees") or (record.trading_fees if record else 0)),
            starting_daily_equity=starting,
            peak_equity=max(starting, account.equity),
            trades_today=session.query(AgentOrder)
            .join(TradePlan)
            .join(TradeCandidate)
            .join(AgentRun)
            .filter(
                AgentRun.agent_config_id == config.id,
                AgentOrder.status == "filled",
                AgentOrder.filled_at >= self._session_day_start_utc(self.resolved_risk_config(config)),
            )
            .count(),
            gross_exposure=sum(abs(p.market_value) for p in positions),
        )

    def _sync_positions(self, session: Session, config: AgentConfig, broker: BrokerAdapter) -> None:
        if isinstance(broker, PaperBrokerAdapter):
            ledger = broker.get_position_ledger()
        else:
            ledger = broker.get_positions()
        live = {p.symbol.upper(): p for p in ledger}
        open_symbols = {
            p.symbol.upper()
            for p in broker.get_positions()
            if abs(float(getattr(p, "quantity", 0) or 0)) > 1e-9
        }
        existing = {
            p.symbol.upper(): p
            for p in session.query(AgentPosition).filter(AgentPosition.user_id == config.user_id).all()
        }
        for symbol, pos in live.items():
            row = existing.get(symbol)
            was_flat = row is None or abs(float(row.quantity or 0)) <= 1e-9
            if row is None:
                row = AgentPosition(
                    user_id=config.user_id,
                    agent_config_id=config.id,
                    symbol=symbol,
                    asset_type=pos.asset_type,
                )
                session.add(row)
                existing[symbol] = row
            row.quantity = pos.quantity
            row.average_entry_price = pos.average_entry_price
            row.current_price = pos.current_price
            row.unrealized_pnl = pos.unrealized_pnl
            row.realized_pnl = pos.realized_pnl
            # Reset holding clock when re-opening a flat symbol so max_holding
            # does not use the first-ever open timestamp from days ago.
            if abs(float(pos.quantity or 0)) > 1e-9 and was_flat:
                row.opened_at = datetime.now(timezone.utc)
            row.updated_at = datetime.now(timezone.utc)
        for symbol, row in existing.items():
            if symbol not in live and symbol not in open_symbols:
                # Fully closed away from ledger: keep realized, clear open mark-to-market.
                row.quantity = 0
                row.unrealized_pnl = 0
                row.updated_at = datetime.now(timezone.utc)
        session.flush()

    def _record_event(
        self,
        session: Session,
        config: AgentConfig,
        event_type: str,
        message: str,
        severity: str = "info",
        payload: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            AgentEvent(
                agent_config_id=config.id,
                event_type=event_type,
                message=message,
                severity=severity,
                payload=payload,
            )
        )
        session.flush()


def build_trading_agent_service(services: Any) -> TradingAgentService:
    forecast = KronosForecastProvider(
        services.kronos,
        getattr(services, "prediction", None),
        getattr(services, "alpaca", None),
    )
    return TradingAgentService(
        forecast_provider=forecast,
        alpaca=getattr(services, "alpaca", None),
        settings=getattr(services, "settings", None),
    )
