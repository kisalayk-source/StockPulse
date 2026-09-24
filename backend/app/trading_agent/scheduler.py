"""Background loop that auto-runs trading agent forecast cycles."""

from __future__ import annotations

import logging
import threading
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any

from app.trading_agent.models import AgentConfig

logger = logging.getLogger("app.trading_agent.scheduler")

DEFAULT_TICK_SECONDS = 15.0


def _credentials_for_config(session: Any, settings: Any, config: AgentConfig):
    """Load Settings-saved Alpaca keys for this agent config, if present."""
    if settings is None:
        return None
    from app.auth import BrokerCredentials
    from app.models import AlpacaCredential
    from app.security import decrypt_secret

    mode = "live" if config.mode == "live" and config.live_trading_enabled else "paper"
    row = (
        session.query(AlpacaCredential)
        .filter(
            AlpacaCredential.user_id == config.user_id,
            AlpacaCredential.mode == mode,
        )
        .one_or_none()
    )
    if row is None:
        return None
    return BrokerCredentials(key=row.key_id, secret=decrypt_secret(settings, row.secret_encrypted))


class AgentCycleScheduler:
    """Daemon worker that cycles all Started (paper/live) agent configs."""

    def __init__(
        self,
        services: Any,
        *,
        tick_seconds: float = DEFAULT_TICK_SECONDS,
    ) -> None:
        self._services = services
        self._tick_seconds = max(1.0, float(tick_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="trading-agent-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("trading_agent_scheduler_started", extra={"tick_seconds": self._tick_seconds})

    def stop(self, *, join_timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)
        self._thread = None
        logger.info("trading_agent_scheduler_stopped")

    def _lock_for(self, config_id: int) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(config_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[config_id] = lock
            return lock

    def _run_loop(self) -> None:
        while not self._stop.wait(self._tick_seconds):
            try:
                self.tick()
            except Exception:
                logger.exception("trading_agent_scheduler_tick_failed")

    def tick(self) -> list[int]:
        """Run due cycles once. Returns config ids that were cycled. Public for tests."""
        from app.db import _SessionLocal

        if _SessionLocal is None:
            return []
        agent = getattr(self._services, "trading_agent", None)
        if agent is None:
            return []

        session = _SessionLocal()
        due_ids: list[int] = []
        try:
            now = datetime.now(timezone.utc)
            market_open = self._market_is_open()
            rows = (
                session.query(AgentConfig)
                .filter(
                    AgentConfig.status.in_(("paper", "live", "paused")),
                    AgentConfig.forecast_enabled.is_(True),
                )
                .all()
            )
            agent = self._services.trading_agent
            for config in rows:
                reason = str((config.risk_config or {}).get("pause_reason") or "")
                if market_open is False and config.status in {"paper", "live"}:
                    agent.pause(session, config)
                    risk = dict(config.risk_config or {})
                    risk["pause_reason"] = "market_closed"
                    config.risk_config = risk
                    session.commit()
                    logger.info(
                        "trading_agent_paused_market_closed",
                        extra={"config_id": config.id},
                    )
                    continue
                if config.status == "paused":
                    if market_open is True and reason == "market_closed":
                        try:
                            agent.resume(session, config)
                        except ValueError:
                            logger.info(
                                "trading_agent_market_resume_blocked",
                                extra={"config_id": config.id},
                            )
                            continue
                        session.commit()
                        due_ids.append(int(config.id))
                    continue
                interval = int(config.cycle_interval_seconds or 300)
                last = config.last_cycle_at
                if last is not None:
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (now - last).total_seconds()
                    if elapsed < interval:
                        continue
                due_ids.append(int(config.id))
        finally:
            session.close()

        cycled: list[int] = []
        for config_id in due_ids:
            if self._stop.is_set():
                break
            if self._run_one(config_id):
                cycled.append(config_id)
        return cycled

    def _market_is_open(self) -> bool | None:
        """True when the session is open, False when closed, None when the clock cannot be read."""
        alpaca = getattr(self._services, "alpaca", None)
        if alpaca is None:
            return True
        try:
            clock = alpaca.market_clock("paper")
        except Exception:
            return None
        if not isinstance(clock, dict) or "is_open" not in clock:
            return None
        return bool(clock.get("is_open"))

    def _run_one(self, config_id: int) -> bool:
        lock = self._lock_for(config_id)
        if not lock.acquire(blocking=False):
            return False

        from app.db import _SessionLocal

        session = None
        try:
            if _SessionLocal is None:
                return False
            session = _SessionLocal()
            config = session.query(AgentConfig).filter(AgentConfig.id == config_id).one_or_none()
            if config is None or config.status not in {"paper", "live"} or not config.forecast_enabled:
                return False

            agent = self._services.trading_agent
            settings = getattr(self._services, "settings", None) or getattr(agent, "settings", None)
            credentials = _credentials_for_config(session, settings, config)
            # Real AlpacaService needs bound keys; FakeAlpaca / paper sim do not.
            needs_creds = getattr(agent, "alpaca", None) is not None and hasattr(
                getattr(agent, "alpaca", None), "_credentials"
            )
            if needs_creds and credentials is None:
                logger.warning(
                    "trading_agent_auto_cycle_skipped_no_credentials",
                    extra={"config_id": config_id, "user_id": config.user_id},
                )
                return False

            from app.auth import use_trading_credentials
            from app.services.providers import ProviderUnavailable

            cred_ctx = use_trading_credentials(credentials) if credentials else nullcontext()
            try:
                with cred_ctx:
                    market_open = True
                    alpaca = getattr(self._services, "alpaca", None)
                    if alpaca is not None:
                        try:
                            clock = alpaca.market_clock("paper")
                            market_open = bool(clock.get("is_open")) if isinstance(clock, dict) else True
                        except Exception:
                            market_open = True

                    agent.run_cycle(session, config, execute=True, market_open=market_open)
                    session.commit()
                    logger.info(
                        "trading_agent_auto_cycle_completed",
                        extra={"config_id": config_id, "market_open": market_open},
                    )
                    return True
            except ProviderUnavailable:
                session.rollback()
                logger.warning(
                    "trading_agent_auto_cycle_skipped_provider_unavailable",
                    extra={"config_id": config_id},
                )
                return False
            except Exception:
                session.rollback()
                # Stamp last_cycle_at so a hard failure does not tight-loop every tick.
                try:
                    session2 = _SessionLocal()
                    try:
                        row = session2.query(AgentConfig).filter(AgentConfig.id == config_id).one_or_none()
                        if row is not None:
                            row.last_cycle_at = datetime.now(timezone.utc)
                            session2.commit()
                    finally:
                        session2.close()
                except Exception:
                    logger.exception(
                        "trading_agent_auto_cycle_stamp_failed",
                        extra={"config_id": config_id},
                    )
                logger.exception(
                    "trading_agent_auto_cycle_failed",
                    extra={"config_id": config_id},
                )
                return False
        finally:
            if session is not None:
                session.close()
            lock.release()


def start_agent_scheduler(services: Any, settings: Any) -> AgentCycleScheduler | None:
    if not getattr(settings, "agent_scheduler_enabled", True):
        return None
    if getattr(settings, "app_environment", "") == "test":
        return None
    tick = float(getattr(settings, "agent_scheduler_tick_seconds", DEFAULT_TICK_SECONDS) or DEFAULT_TICK_SECONDS)
    scheduler = AgentCycleScheduler(services, tick_seconds=tick)
    scheduler.start()
    return scheduler
