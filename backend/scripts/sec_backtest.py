"""Offline SEC accumulation backtest CLI."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from app.config import get_settings
from app.db import init_db, reset_db_state
from app.dependencies import build_services
from app.sec.backtest.runner import run_accumulation_backtest
from sqlalchemy.orm import Session
from app.db import get_session


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SEC accumulation backtest")
    parser.add_argument("ticker", help="Ticker symbol")
    parser.add_argument("--days", type=int, default=365, help="Lookback days for evaluation grid")
    args = parser.parse_args()

    settings = get_settings()
    init_db(settings)
    services = build_services(settings)
    session_gen = get_session()
    session: Session = next(session_gen)
    try:
        bars = services.alpaca.bars(args.ticker.upper(), "1Day", None, None, 600)
        end = date.today()
        start = end - timedelta(days=args.days)
        evaluation_dates = [start + timedelta(days=i * 30) for i in range(max(args.days // 30, 1))]
        payload = run_accumulation_backtest(session, args.ticker.upper(), bars, evaluation_dates)
        print(json.dumps(payload, indent=2))
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass
        reset_db_state()


if __name__ == "__main__":
    main()
