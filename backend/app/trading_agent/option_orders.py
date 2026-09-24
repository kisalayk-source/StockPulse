"""Pick tradable OCC contracts for option strategy candidates. No broker I/O."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

OCC_OPTION_SYMBOL = re.compile(r"^([A-Z]{1,6})\d{6}[CP]\d{8}$")


def is_occ_symbol(symbol: str | None) -> bool:
    return bool(OCC_OPTION_SYMBOL.fullmatch(str(symbol or "").upper()))


def occ_underlying(symbol: str | None) -> str | None:
    match = OCC_OPTION_SYMBOL.fullmatch(str(symbol or "").upper())
    return match.group(1) if match else None


def _field(contract: Any, name: str) -> Any:
    if isinstance(contract, dict):
        return contract.get(name)
    return getattr(contract, name, None)


def _expiration(contract: Any) -> date | None:
    raw = _field(contract, "expiration_date")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _strike(contract: Any) -> float | None:
    try:
        value = float(_field(contract, "strike_price"))
    except (TypeError, ValueError):
        return None
    return value if value == value else None


def _tradable(contract: Any) -> bool:
    flag = _field(contract, "tradable")
    if flag is None:
        return True
    return bool(flag)


def _right(contract: Any) -> str:
    raw = _field(contract, "type") or _field(contract, "right") or ""
    text = str(getattr(raw, "value", raw)).lower()
    if "put" in text:
        return "put"
    if "call" in text:
        return "call"
    return text


def _symbol(contract: Any) -> str:
    return str(_field(contract, "symbol") or "").upper()


def _eligible(
    contracts: list[Any],
    *,
    today: date,
    min_dte: int,
    max_dte: int,
    right: str,
) -> list[tuple[Any, date, int, float]]:
    rows: list[tuple[Any, date, int, float]] = []
    for contract in contracts:
        if not _tradable(contract):
            continue
        if _right(contract) != right:
            continue
        if not is_occ_symbol(_symbol(contract)):
            continue
        expiration = _expiration(contract)
        strike = _strike(contract)
        if expiration is None or strike is None:
            continue
        dte = (expiration - today).days
        if dte < min_dte or dte > max_dte:
            continue
        rows.append((contract, expiration, dte, strike))
    return rows


def _closest_expiration(
    rows: list[tuple[Any, date, int, float]],
    target_dte: int,
) -> date | None:
    best: date | None = None
    best_distance: int | None = None
    for _contract, expiration, dte, _strike in rows:
        distance = abs(dte - target_dte)
        if best is None or best_distance is None or distance < best_distance or (
            distance == best_distance and expiration < best
        ):
            best = expiration
            best_distance = distance
    return best


def _closest_strike(
    rows: list[tuple[Any, date, int, float]],
    expiration: date,
    target: float,
    *,
    above: float | None = None,
) -> Any | None:
    pool = [
        (contract, strike)
        for contract, exp, _dte, strike in rows
        if exp == expiration and (above is None or strike > above)
    ]
    if not pool:
        return None
    contract, _strike = min(pool, key=lambda item: (abs(item[1] - target), item[1], _symbol(item[0])))
    return contract


def select_single_contract(
    contracts: list[Any],
    *,
    right: str,
    target_strike: float,
    target_dte: int,
    today: date,
    min_dte: int,
    max_dte: int,
) -> dict[str, Any] | None:
    rows = _eligible(contracts, today=today, min_dte=min_dte, max_dte=max_dte, right=right)
    expiration = _closest_expiration(rows, target_dte)
    if expiration is None:
        return None
    chosen = _closest_strike(rows, expiration, target_strike)
    if chosen is None:
        return None
    dte = next(item[2] for item in rows if item[0] is chosen)
    return {
        "symbol": _symbol(chosen),
        "strike": _strike(chosen),
        "expiration": expiration,
        "days_to_expiration": dte,
        "right": right,
    }


def select_bull_call_spread(
    contracts: list[Any],
    *,
    long_strike: float,
    short_strike: float,
    target_dte: int,
    today: date,
    min_dte: int,
    max_dte: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    rows = _eligible(contracts, today=today, min_dte=min_dte, max_dte=max_dte, right="call")
    expiration = _closest_expiration(rows, target_dte)
    if expiration is None:
        return None
    long_contract = _closest_strike(rows, expiration, long_strike)
    if long_contract is None:
        return None
    long_px = _strike(long_contract)
    if long_px is None:
        return None
    short_contract = _closest_strike(rows, expiration, short_strike, above=long_px)
    if short_contract is None:
        return None
    dte = next(item[2] for item in rows if item[0] is long_contract)
    def pack(contract: Any) -> dict[str, Any]:
        return {
            "symbol": _symbol(contract),
            "strike": _strike(contract),
            "expiration": expiration,
            "days_to_expiration": dte,
            "right": "call",
        }
    return pack(long_contract), pack(short_contract)


def select_bear_put_spread(
    contracts: list[Any],
    *,
    long_strike: float,
    short_strike: float,
    target_dte: int,
    today: date,
    min_dte: int,
    max_dte: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Long put is the higher strike. Short put is strictly below it."""
    rows = _eligible(contracts, today=today, min_dte=min_dte, max_dte=max_dte, right="put")
    expiration = _closest_expiration(rows, target_dte)
    if expiration is None:
        return None
    long_contract = _closest_strike(rows, expiration, long_strike)
    if long_contract is None:
        return None
    long_px = _strike(long_contract)
    if long_px is None:
        return None
    pool = [
        (contract, strike)
        for contract, exp, _dte, strike in rows
        if exp == expiration and strike < long_px
    ]
    if not pool:
        return None
    short_contract, _short_px = min(pool, key=lambda item: (abs(item[1] - short_strike), -item[1], _symbol(item[0])))
    dte = next(item[2] for item in rows if item[0] is long_contract)

    def pack(contract: Any) -> dict[str, Any]:
        return {
            "symbol": _symbol(contract),
            "strike": _strike(contract),
            "expiration": expiration,
            "days_to_expiration": dte,
            "right": "put",
        }

    return pack(long_contract), pack(short_contract)


def fit_option_contracts(quantity: float, unit_price: float, risk: dict[str, Any]) -> int | None:
    """Shrink contract count so premium and max loss fit the risk limits."""
    unit = float(unit_price) * 100.0
    if unit <= 0:
        return None
    contracts = int(quantity)
    max_premium = float(risk.get("max_premium_per_trade") or 0)
    max_loss = float(risk.get("max_loss_per_options_position") or 0)
    max_qty = int(float(risk.get("max_order_quantity") or 0) or 0)
    if max_premium > 0:
        contracts = min(contracts, int(max_premium // unit))
    if max_loss > 0:
        contracts = min(contracts, int(max_loss // unit))
    if max_qty > 0:
        contracts = min(contracts, max_qty)
    if contracts < 1:
        return None
    return contracts


def _quote_px(quote: dict[str, Any] | None, *names: str) -> float | None:
    if not quote:
        return None
    for name in names:
        try:
            value = float(quote.get(name))
        except (TypeError, ValueError):
            continue
        if value == value and value > 0:
            return value
    return None


def price_single(quote: dict[str, Any] | None) -> tuple[float, float | None] | None:
    """Return (ask, bid_ask_spread) for a long option. Ask is required."""
    ask = _quote_px(quote, "ask")
    if ask is None:
        return None
    bid = _quote_px(quote, "bid")
    spread = (ask - bid) if bid is not None and ask >= bid else None
    return ask, spread


def price_credit(quote: dict[str, Any] | None) -> tuple[float, float | None] | None:
    """Return (bid, bid_ask_spread) for a short option. Bid is required."""
    bid = _quote_px(quote, "bid")
    if bid is None:
        return None
    ask = _quote_px(quote, "ask")
    spread = (ask - bid) if ask is not None and ask >= bid else None
    return bid, spread


def quote_greek(quote: dict[str, Any] | None, name: str) -> float | None:
    if not quote:
        return None
    try:
        value = float(quote.get(name))
    except (TypeError, ValueError):
        return None
    return value if value == value else None


def price_bull_call_spread(
    long_quote: dict[str, Any] | None,
    short_quote: dict[str, Any] | None,
    *,
    width: float,
) -> tuple[float, float | None] | None:
    """Return (debit, package spread). Debit must be positive and below the strike width."""
    long_ask = _quote_px(long_quote, "ask")
    short_bid = _quote_px(short_quote, "bid")
    if long_ask is None or short_bid is None or width <= 0:
        return None
    debit = long_ask - short_bid
    if debit <= 0 or debit >= width:
        return None
    long_bid = _quote_px(long_quote, "bid")
    short_ask = _quote_px(short_quote, "ask")
    package = None
    if long_bid is not None and short_ask is not None:
        package = (long_ask - long_bid) + (short_ask - short_bid)
    return debit, package
