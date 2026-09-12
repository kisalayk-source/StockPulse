"""Broker execution abstraction — paper and live share the same interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4


@dataclass
class OrderRequest:
    symbol: str
    side: str
    quantity: float
    order_type: str = "market"
    limit_price: float | None = None
    time_in_force: str = "day"
    asset_type: str = "equity"
    contract_symbol: str | None = None
    position_intent: str | None = None
    idempotency_key: str | None = None
    mode: str = "paper"


@dataclass
class OrderResult:
    broker_order_id: str
    status: str
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    submitted_at: str | None = None
    filled_at: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker_order_id": self.broker_order_id,
            "status": self.status,
            "filled_quantity": self.filled_quantity,
            "average_fill_price": self.average_fill_price,
            "submitted_at": self.submitted_at,
            "filled_at": self.filled_at,
            "error_message": self.error_message,
            "raw": self.raw,
        }


@dataclass
class AccountSnapshot:
    equity: float
    cash: float
    buying_power: float
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    symbol: str
    quantity: float
    average_entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    asset_type: str = "equity"
    market_value: float = 0.0


class BrokerAdapter(Protocol):
    def submit_order(self, order: OrderRequest) -> OrderResult:
        ...

    def cancel_order(self, order_id: str) -> None:
        ...

    def get_positions(self) -> list[Position]:
        ...

    def get_account(self) -> AccountSnapshot:
        ...

    def get_open_orders(self) -> list[dict[str, Any]]:
        ...


class PaperBrokerAdapter:
    """Simulated broker for paper trading — never hits a live exchange."""

    def __init__(
        self,
        *,
        starting_cash: float = 25_000.0,
        prices: dict[str, float] | None = None,
    ) -> None:
        self.cash = float(starting_cash)
        self.starting_cash = float(starting_cash)
        self.prices = dict(prices or {})
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, OrderResult] = {}
        self.open_orders: dict[str, dict[str, Any]] = {}
        self.realized_pnl = 0.0
        self.day_start_realized = 0.0
        self.fees = 0.0
        self._seen_keys: set[str] = set()

    def mark_day_start(self) -> None:
        """Capture realized P/L baseline for daily-loss calculations."""
        self.day_start_realized = float(self.realized_pnl)

    def today_realized_pnl(self) -> float:
        return float(self.realized_pnl) - float(self.day_start_realized)

    def set_price(self, symbol: str, price: float) -> None:
        self.prices[symbol.upper()] = float(price)
        pos = self.positions.get(symbol.upper())
        if pos:
            pos.current_price = float(price)
            multiplier = 100.0 if pos.asset_type == "option" else 1.0
            pos.market_value = pos.quantity * pos.current_price * multiplier
            pos.unrealized_pnl = (
                (pos.current_price - pos.average_entry_price) * pos.quantity * multiplier
            )

    def submit_order(self, order: OrderRequest) -> OrderResult:
        key = order.idempotency_key or uuid4().hex
        if key in self._seen_keys:
            for existing in self.orders.values():
                if existing.raw.get("idempotency_key") == key:
                    return existing
            raise ValueError("Duplicate order idempotency key")
        self._seen_keys.add(key)

        symbol = (order.contract_symbol or order.symbol).upper()
        price = order.limit_price or self.prices.get(symbol) or self.prices.get(order.symbol.upper())
        now = datetime.now(timezone.utc).isoformat()
        order_id = f"paper-{uuid4().hex[:12]}"

        if price is None or price <= 0:
            result = OrderResult(
                broker_order_id=order_id,
                status="rejected",
                submitted_at=now,
                error_message="No market price available",
                raw={"idempotency_key": key},
            )
            self.orders[order_id] = result
            return result

        multiplier = 100.0 if order.asset_type == "option" else 1.0
        cost = abs(order.quantity) * price * multiplier
        side = order.side.lower()

        if side == "buy" and cost > self.cash:
            result = OrderResult(
                broker_order_id=order_id,
                status="rejected",
                submitted_at=now,
                error_message="Insufficient buying power",
                raw={"idempotency_key": key},
            )
            self.orders[order_id] = result
            return result

        # Fill immediately at mark (paper simulation)
        fill_qty = float(order.quantity)
        if side == "buy":
            self.cash -= cost
            existing = self.positions.get(symbol)
            if existing:
                total_qty = existing.quantity + fill_qty
                avg = (
                    (existing.average_entry_price * existing.quantity + price * fill_qty) / total_qty
                    if total_qty
                    else price
                )
                existing.quantity = total_qty
                existing.average_entry_price = avg
                existing.current_price = price
                existing.market_value = total_qty * price * multiplier
                existing.unrealized_pnl = (price - avg) * total_qty * multiplier
            else:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=fill_qty,
                    average_entry_price=price,
                    current_price=price,
                    market_value=fill_qty * price * multiplier,
                    asset_type=order.asset_type,
                )
        else:
            existing = self.positions.get(symbol)
            held = existing.quantity if existing else 0.0
            sell_qty = min(fill_qty, held) if held > 0 else 0.0
            if sell_qty <= 0:
                result = OrderResult(
                    broker_order_id=order_id,
                    status="rejected",
                    submitted_at=now,
                    error_message="No long position to sell",
                    raw={"idempotency_key": key},
                )
                self.orders[order_id] = result
                return result
            proceeds = sell_qty * price * multiplier
            realized = (price - existing.average_entry_price) * sell_qty * multiplier
            self.cash += proceeds
            self.realized_pnl += realized
            existing.realized_pnl += realized
            existing.quantity -= sell_qty
            if existing.quantity <= 1e-9:
                del self.positions[symbol]
            else:
                existing.current_price = price
                existing.market_value = existing.quantity * price * multiplier
                existing.unrealized_pnl = (
                    (price - existing.average_entry_price) * existing.quantity * multiplier
                )
            fill_qty = sell_qty

        result = OrderResult(
            broker_order_id=order_id,
            status="filled",
            filled_quantity=fill_qty,
            average_fill_price=price,
            submitted_at=now,
            filled_at=now,
            raw={"idempotency_key": key, "mode": "paper"},
        )
        self.orders[order_id] = result
        return result

    def cancel_order(self, order_id: str) -> None:
        self.open_orders.pop(order_id, None)
        existing = self.orders.get(order_id)
        if existing and existing.status in {"pending", "accepted", "new"}:
            existing.status = "canceled"

    def get_positions(self) -> list[Position]:
        return list(self.positions.values())

    def get_account(self) -> AccountSnapshot:
        positions_value = sum(p.market_value for p in self.positions.values())
        equity = self.cash + positions_value
        return AccountSnapshot(
            equity=equity,
            cash=self.cash,
            buying_power=self.cash,
            raw={
                "realized_pnl": self.realized_pnl,
                "today_realized_pnl": self.today_realized_pnl(),
                "fees": self.fees,
            },
        )

    def get_open_orders(self) -> list[dict[str, Any]]:
        return list(self.open_orders.values())


class AlpacaBrokerAdapter:
    """Thin adapter over existing AlpacaService for live/paper broker I/O."""

    _TERMINAL_STATUSES = frozenset(
        {"filled", "canceled", "cancelled", "expired", "rejected", "done_for_day"}
    )

    def __init__(self, alpaca: Any, mode: str = "paper") -> None:
        self.alpaca = alpaca
        self.mode = mode

    def submit_order(self, order: OrderRequest) -> OrderResult:
        from types import SimpleNamespace

        now = datetime.now(timezone.utc).isoformat()
        try:
            if order.asset_type == "option" or order.contract_symbol:
                payload = SimpleNamespace(
                    mode=self.mode,
                    contract_symbol=order.contract_symbol or order.symbol,
                    side=order.side,
                    qty=order.quantity,
                    type=order.order_type,
                    limit_price=order.limit_price,
                    time_in_force=order.time_in_force,
                    position_intent=order.position_intent or "buy_to_open",
                )
                raw = self.alpaca.submit_option_order(payload)
            else:
                payload = SimpleNamespace(
                    mode=self.mode,
                    symbol=order.symbol,
                    side=order.side,
                    qty=order.quantity,
                    notional=None,
                    type=order.order_type,
                    limit_price=order.limit_price,
                    stop_price=None,
                    time_in_force=order.time_in_force,
                    extended_hours=False,
                )
                raw = self.alpaca.submit_equity_order(payload)
            if not isinstance(raw, dict):
                raw = {"result": raw}
            raw = self._await_fill(raw)
            status = str(raw.get("status") or "accepted")
            return OrderResult(
                broker_order_id=str(raw.get("id") or uuid4().hex),
                status=status,
                filled_quantity=float(raw.get("filled_qty") or 0),
                average_fill_price=float(raw["filled_avg_price"]) if raw.get("filled_avg_price") else None,
                submitted_at=now,
                filled_at=raw.get("filled_at"),
                raw=raw,
            )
        except Exception as exc:
            return OrderResult(
                broker_order_id=f"error-{uuid4().hex[:8]}",
                status="rejected",
                submitted_at=now,
                error_message=str(exc),
            )

    def _await_fill(self, raw: dict[str, Any], *, attempts: int = 8, delay: float = 0.25) -> dict[str, Any]:
        """Poll briefly so paper market orders resolve to filled when Alpaca is fast."""
        import time

        status = str(raw.get("status") or "").lower()
        order_id = raw.get("id")
        if not order_id or status in self._TERMINAL_STATUSES:
            return raw
        get_order = getattr(self.alpaca, "get_order", None)
        if not callable(get_order):
            return raw
        latest = raw
        for _ in range(attempts):
            time.sleep(delay)
            try:
                polled = get_order(str(order_id), self.mode)
            except Exception:
                break
            if isinstance(polled, dict):
                latest = polled
                status = str(polled.get("status") or "").lower()
                if status in self._TERMINAL_STATUSES:
                    return polled
        return latest

    def cancel_order(self, order_id: str) -> None:
        self.alpaca.cancel_order(order_id, self.mode)

    def get_positions(self) -> list[Position]:
        rows = self.alpaca.positions(self.mode)
        out: list[Position] = []
        for row in rows or []:
            data = row if isinstance(row, dict) else {
                "symbol": getattr(row, "symbol", None),
                "qty": getattr(row, "qty", 0),
                "avg_entry_price": getattr(row, "avg_entry_price", 0),
                "current_price": getattr(row, "current_price", 0),
                "unrealized_pl": getattr(row, "unrealized_pl", 0),
                "market_value": getattr(row, "market_value", 0),
            }
            qty = float(data.get("qty") or data.get("quantity") or 0)
            out.append(
                Position(
                    symbol=str(data.get("symbol") or "").upper(),
                    quantity=qty,
                    average_entry_price=float(data.get("avg_entry_price") or data.get("average_entry_price") or 0),
                    current_price=float(data.get("current_price") or 0),
                    unrealized_pnl=float(data.get("unrealized_pl") or data.get("unrealized_pnl") or 0),
                    market_value=float(data.get("market_value") or 0),
                )
            )
        return out

    def get_account(self) -> AccountSnapshot:
        acct = self.alpaca.account(self.mode)
        data = acct if isinstance(acct, dict) else {
            "equity": getattr(acct, "equity", 0),
            "cash": getattr(acct, "cash", 0),
            "buying_power": getattr(acct, "buying_power", 0),
        }
        return AccountSnapshot(
            equity=float(data.get("equity") or 0),
            cash=float(data.get("cash") or 0),
            buying_power=float(data.get("buying_power") or 0),
            raw=data if isinstance(data, dict) else {},
        )

    def get_open_orders(self) -> list[dict[str, Any]]:
        rows = self.alpaca.orders(self.mode, status="open", limit=100)
        return [r if isinstance(r, dict) else {"id": getattr(r, "id", None)} for r in rows or []]
