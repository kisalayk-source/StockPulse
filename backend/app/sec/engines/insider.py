from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.sec.models import NormalizedEvent
from app.sec.normalization import is_discretionary_insider


def score_insider(events: list[NormalizedEvent], config: dict[str, Any]) -> tuple[float, list[str]]:
    insider_events = [event for event in events if event.component == "insider"]
    if not insider_events:
        return 50.0, []
    buys = 0
    sells = 0
    buy_value = 0.0
    sell_value = 0.0
    ceo_buy = False
    cfo_buy = False
    director_buy = False
    evidence: list[str] = []
    cluster_cfg = config.get("insider_cluster", {})
    window_days = int(cluster_cfg.get("window_days", 30))
    min_insiders = int(cluster_cfg.get("min_insiders", 3))
    today = date.today()
    window_start = today - timedelta(days=window_days)
    buyers_in_window: set[str] = set()
    sellers_in_window: set[str] = set()

    for event in insider_events:
        meta = event.metadata or {}
        if not is_discretionary_insider(event.event_type):
            continue
        name = str(meta.get("insider_name", "insider"))
        title = str(meta.get("insider_title", "")).upper()
        value = float(meta.get("value") or 0.0)
        txn_date = event.filing_date or event.reporting_period
        if event.event_type == "DISCRETIONARY_BUY":
            buys += 1
            buy_value += value
            if txn_date and txn_date >= window_start:
                buyers_in_window.add(name)
            if "CEO" in title:
                ceo_buy = True
            if "CFO" in title:
                cfo_buy = True
            if "DIRECTOR" in title:
                director_buy = True
        elif event.event_type == "DISCRETIONARY_SELL":
            sells += 1
            sell_value += value
            if txn_date and txn_date >= window_start:
                sellers_in_window.add(name)

    if ceo_buy:
        evidence.append("+ CEO discretionary purchase reported")
    if cfo_buy:
        evidence.append("+ CFO discretionary purchase reported")
    if director_buy:
        evidence.append("+ Director discretionary purchase reported")
    if len(buyers_in_window) >= min_insiders:
        evidence.append(f"+ Insider cluster buy ({len(buyers_in_window)} insiders within {window_days} days)")
    if len(sellers_in_window) >= min_insiders:
        evidence.append(f"- Insider cluster sell ({len(sellers_in_window)} insiders within {window_days} days)")
    if buys:
        evidence.append(f"+ {buys} discretionary insider purchases")
    if sells:
        evidence.append(f"- {sells} discretionary insider sales")

    net = buys - sells
    value_net = buy_value - sell_value
    raw = 50.0 + net * 8.0 + (value_net / 1_000_000.0) * 2.0
    if len(buyers_in_window) >= min_insiders:
        raw += 10.0
    if len(sellers_in_window) >= min_insiders:
        raw -= 10.0
    return max(0.0, min(100.0, raw)), evidence
