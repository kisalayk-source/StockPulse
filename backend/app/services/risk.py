from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _account_map(account: Any) -> dict[str, Any]:
    if isinstance(account, dict):
        return account
    return {
        "equity": getattr(account, "equity", None),
        "last_equity": getattr(account, "last_equity", None),
        "buying_power": getattr(account, "buying_power", None),
        "cash": getattr(account, "cash", None),
    }


def estimated_notional(order: Any, snapshot: dict[str, Any] | None = None) -> float | None:
    snapshot = snapshot or {}
    notional = _number(getattr(order, "notional", None))
    if notional is not None:
        return notional
    qty = _number(getattr(order, "qty", None))
    price = (
        _number(getattr(order, "limit_price", None))
        or _number(getattr(order, "stop_price", None))
        or _number(snapshot.get("current_price"))
        or _number(snapshot.get("ask"))
    )
    if qty is None or price is None:
        return None
    multiplier = 100.0 if getattr(order, "contract_symbol", None) else 1.0
    return qty * price * multiplier


def spread_bps(snapshot: dict[str, Any] | None) -> float | None:
    snapshot = snapshot or {}
    bid = _number(snapshot.get("bid"))
    ask = _number(snapshot.get("ask"))
    if bid and ask and ask >= bid:
        mid = (bid + ask) / 2.0
        if mid:
            return (ask - bid) / mid * 10_000.0
    return None


def average_daily_volume(snapshot: dict[str, Any] | None) -> float | None:
    snapshot = snapshot or {}
    return _number(snapshot.get("average_daily_volume"))


def daily_pnl_pct(account: Any) -> float | None:
    data = _account_map(account)
    equity = _number(data.get("equity"))
    last_equity = _number(data.get("last_equity"))
    if equity is None or last_equity in (None, 0):
        return None
    return equity / last_equity - 1.0


def position_value(positions: list[Any], symbol: str) -> float:
    ticker = symbol.upper()
    total = 0.0
    for item in positions or []:
        payload = item if isinstance(item, dict) else {
            "symbol": getattr(item, "symbol", None),
            "market_value": getattr(item, "market_value", None),
        }
        if str(payload.get("symbol") or "").upper() != ticker:
            continue
        total += abs(_number(payload.get("market_value")) or 0.0)
    return total


def position_quantity(positions: list[Any], symbol: str) -> float:
    ticker = symbol.upper()
    total = 0.0
    for item in positions or []:
        payload = item if isinstance(item, dict) else {
            "symbol": getattr(item, "symbol", None),
            "qty": getattr(item, "qty", None),
        }
        if str(payload.get("symbol") or "").upper() == ticker:
            total += _number(payload.get("qty")) or 0.0
    return total


def gross_exposure(positions: list[Any]) -> float:
    total = 0.0
    for item in positions or []:
        payload = item if isinstance(item, dict) else {
            "market_value": getattr(item, "market_value", None),
        }
        total += abs(_number(payload.get("market_value")) or 0.0)
    return total


def account_risk_status(account: Any, positions: list[Any], settings: Any) -> dict[str, Any]:
    data = _account_map(account)
    equity = _number(data.get("equity"))
    pnl = daily_pnl_pct(account)
    halted = pnl is not None and pnl <= -float(settings.risk_max_daily_loss_pct)
    return {
        "equity": equity,
        "buying_power": _number(data.get("buying_power")),
        "daily_pnl_pct": pnl,
        "new_buys_halted": halted,
        "open_positions": len(positions or []),
        "gross_exposure": gross_exposure(positions),
        "limits": {
            "max_position_pct": settings.risk_max_position_pct,
            "max_option_debit_pct": settings.risk_max_option_debit_pct,
            "max_daily_loss_pct": settings.risk_max_daily_loss_pct,
            "max_spread_bps": settings.risk_max_spread_bps,
            "min_adv_shares": settings.risk_min_adv_shares,
            "max_gross_pct": settings.risk_max_gross_pct,
        },
    }


def check_order_risk(
    order: Any,
    *,
    account: Any,
    positions: list[Any],
    snapshot: dict[str, Any] | None,
    settings: Any,
    option: bool = False,
) -> dict[str, Any]:
    """Raise ValueError when a hard limit is breached. Return a preview payload."""
    data = _account_map(account)
    equity = _number(data.get("equity"))
    buying_power = _number(data.get("buying_power"))
    side = getattr(getattr(order, "side", None), "value", getattr(order, "side", None))
    cost = estimated_notional(order, snapshot)
    pnl = daily_pnl_pct(account)
    spread = spread_bps(snapshot)
    volume = average_daily_volume(snapshot)
    symbol = str(
        getattr(order, "symbol", None)
        or (snapshot or {}).get("symbol")
        or getattr(order, "contract_symbol", "")
        or ""
    ).upper()
    warnings: list[str] = []
    intent = getattr(
        getattr(order, "position_intent", None),
        "value",
        getattr(order, "position_intent", None),
    )
    requested_qty = _number(getattr(order, "qty", None))
    requested_notional = _number(getattr(order, "notional", None))

    if side == "sell" and option:
        contract = str(getattr(order, "contract_symbol", "") or "").upper()
        intent = intent or "sell_to_close"
        held = position_quantity(positions, contract)
        if intent == "sell_to_open" and not bool(settings.allow_uncovered_options):
            raise ValueError("sell_to_open is disabled; uncovered option writing is not allowed")
        if intent == "sell_to_close" and (held <= 0 or (requested_qty and requested_qty > held)):
            raise ValueError("sell_to_close quantity exceeds the long option position")
    elif side == "buy" and option and intent == "buy_to_close":
        contract = str(getattr(order, "contract_symbol", "") or "").upper()
        held = position_quantity(positions, contract)
        if held >= 0 or (requested_qty and requested_qty > abs(held)):
            raise ValueError("buy_to_close quantity exceeds the short option position")
    elif side == "sell" and not option and not bool(settings.allow_short_selling):
        held_qty = position_quantity(positions, symbol)
        held_value = position_value(positions, symbol)
        if requested_qty is not None and requested_qty > max(held_qty, 0.0):
            raise ValueError("Sell quantity exceeds the long position; short selling is disabled")
        if requested_notional is not None and (
            held_qty <= 0 or requested_notional > held_value
        ):
            raise ValueError("Sell notional exceeds the long position; short selling is disabled")

    if side == "buy" and pnl is not None and pnl <= -float(settings.risk_max_daily_loss_pct):
        raise ValueError(
            f"New buys halted: session loss {pnl:.2%} exceeds "
            f"{float(settings.risk_max_daily_loss_pct):.2%} limit"
        )
    if side == "buy" and cost is not None and buying_power is not None and cost > buying_power:
        raise ValueError(
            f"Estimated order value {cost:.2f} exceeds buying power {buying_power:.2f}"
        )
    if side == "buy" and equity and cost is not None:
        current = position_value(positions, symbol)
        projected_pct = (current + cost) / equity
        limit = (
            float(settings.risk_max_option_debit_pct)
            if option
            else float(settings.risk_max_position_pct)
        )
        if projected_pct > limit:
            kind = "option debit" if option else "position"
            raise ValueError(
                f"Estimated {kind} {projected_pct:.1%} of equity exceeds {limit:.1%} limit"
            )
        gross_pct = (gross_exposure(positions) + cost) / equity
        if gross_pct > float(settings.risk_max_gross_pct):
            raise ValueError(
                f"Gross exposure {gross_pct:.1%} of equity exceeds "
                f"{float(settings.risk_max_gross_pct):.1%} limit"
            )
    if side == "buy" and spread is not None and spread > float(settings.risk_max_spread_bps):
        raise ValueError(
            f"Quoted spread {spread:.1f} bps exceeds {float(settings.risk_max_spread_bps):.0f} bps limit"
        )
    if side == "buy" and volume is not None and volume < float(settings.risk_min_adv_shares):
        raise ValueError(
            f"Average daily volume {volume:.0f} is below the "
            f"{float(settings.risk_min_adv_shares):.0f} share liquidity floor"
        )
    if getattr(getattr(order, "type", None), "value", getattr(order, "type", None)) == "market" and cost and cost >= 5_000:
        warnings.append("Large market order: consider a limit to reduce slippage")

    status = account_risk_status(account, positions, settings)
    position_pct = None
    if equity and cost is not None:
        current = position_value(positions, symbol)
        position_pct = (current + (cost if side == "buy" else 0.0)) / equity
    return {
        "ok": True,
        "estimated_cost": cost,
        "position_pct": position_pct,
        "spread_bps": spread,
        "adv_shares": volume,
        "average_daily_volume_shares": volume,
        "daily_pnl_pct": pnl,
        "warnings": warnings,
        "risk": status,
    }
