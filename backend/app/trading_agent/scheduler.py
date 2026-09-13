"""Background loop that auto-runs trading agent forecast cycles."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.trading_agent.models import AgentConfig

logger = logging.getLogger("app.trading_agent.scheduler")

DEFAULT_TICK_SECONDS = 15.0


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
            rows = (
                session.query(AgentConfig)
                .filter(
                    AgentConfig.status.in_(("paper", "live")),
                    AgentConfig.forecast_enabled.is_(True),
                )
                .all()
            )
            for config in rows:
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

            market_open = True
            alpaca = getattr(self._services, "alpaca", None)
            if alpaca is not None:
                try:
                    clock = alpaca.market_clock("paper")
                    market_open = bool(clock.get("is_open")) if isinstance(clock, dict) else True
                except Exception:
                    market_open = True

            agent = self._services.trading_agent
            try:
                agent.run_cycle(session, config, execute=True, market_open=market_open)
                session.commit()
                logger.info(
                    "trading_agent_auto_cycle_completed",
                    extra={"config_id": config_id, "market_open": market_open},
                )
                return True
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
