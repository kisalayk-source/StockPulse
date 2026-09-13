"""Insider (Form 4) flow features — PIT-safe (MVP-3)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ml.features.feature_schema import normalize_feature_dict
from ml.features.sec._common import as_of_date, event_available_date, filter_events_as_of, to_float

_DISCRETIONARY = {"DISCRETIONARY_BUY", "DISCRETIONARY_SELL"}
_CLUSTER_WINDOW_DAYS = 30
_CLUSTER_MIN_INSIDERS = 3


def insider_flow_features(
    events: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> dict[str, float]:
    """Only events with filing_date / published_at <= as_of are used."""
    pit = filter_events_as_of(events, as_of, component="insider")
    discretionary = [e for e in pit if str(e.get("event_type") or "") in _DISCRETIONARY]
    if not discretionary:
        return {}

    cutoff = as_of_date(as_of)
    window_start = cutoff - timedelta(days=_CLUSTER_WINDOW_DAYS)
    buys = 0
    sells = 0
    buy_value = 0.0
    sell_value = 0.0
    buyers_in_window: set[str] = set()
    sellers_in_window: set[str] = set()
    ceo_buy = 0.0
    cfo_buy = 0.0

    for event in discretionary:
        et = str(event.get("event_type") or "")
        meta = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        name = str(meta.get("insider_name") or "insider")
        title = str(meta.get("insider_title") or "").upper()
        value = to_float(meta.get("value"), 0.0) or 0.0
        txn_date = event_available_date(event)
        if et == "DISCRETIONARY_BUY":
            buys += 1
            buy_value += value
            if txn_date is not None and txn_date >= window_start:
                buyers_in_window.add(name)
            if "CEO" in title:
                ceo_buy = 1.0
            if "CFO" in title:
                cfo_buy = 1.0
        elif et == "DISCRETIONARY_SELL":
            sells += 1
            sell_value += value
            if txn_date is not None and txn_date >= window_start:
                sellers_in_window.add(name)

    net = buys - sells
    value_net = buy_value - sell_value
    cluster_buy = 1.0 if len(buyers_in_window) >= _CLUSTER_MIN_INSIDERS else 0.0
    cluster_sell = 1.0 if len(sellers_in_window) >= _CLUSTER_MIN_INSIDERS else 0.0
    raw = 50.0 + net * 8.0 + (value_net / 1_000_000.0) * 2.0
    if cluster_buy:
        raw += 10.0
    if cluster_sell:
        raw -= 10.0
    flow_score = max(0.0, min(100.0, raw))

    return normalize_feature_dict(
        {
            "insider_buy_count": float(buys),
            "insider_sell_count": float(sells),
            "insider_net_count": float(net),
            "insider_buy_value": buy_value,
            "insider_sell_value": sell_value,
            "insider_net_value": value_net,
            "insider_cluster_buy": cluster_buy,
            "insider_cluster_sell": cluster_sell,
            "insider_ceo_buy": ceo_buy,
            "insider_cfo_buy": cfo_buy,
            "insider_flow_score": flow_score,
        }
    )
