from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TradingMode(str, Enum):
    paper = "paper"
    live = "live"


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class OrderType(str, Enum):
    market = "market"
    limit = "limit"
    stop = "stop"
    stop_limit = "stop_limit"


class TimeInForce(str, Enum):
    day = "day"
    gtc = "gtc"
    opg = "opg"
    cls = "cls"
    ioc = "ioc"
    fok = "fok"


class OptionPositionIntent(str, Enum):
    buy_to_open = "buy_to_open"
    buy_to_close = "buy_to_close"
    sell_to_open = "sell_to_open"
    sell_to_close = "sell_to_close"


class EquityOrderRequest(BaseModel):
    mode: TradingMode
    symbol: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z.\-]+$")
    side: OrderSide
    type: OrderType = OrderType.market
    time_in_force: TimeInForce = TimeInForce.day
    qty: float | None = Field(default=None, gt=0)
    notional: float | None = Field(default=None, gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    extended_hours: bool = False
    live_confirmation_token: str | None = None

    @model_validator(mode="after")
    def validate_order(self) -> "EquityOrderRequest":
        if (self.qty is None) == (self.notional is None):
            raise ValueError("Provide exactly one of qty or notional")
        if self.type in {OrderType.limit, OrderType.stop_limit} and self.limit_price is None:
            raise ValueError("limit_price is required for limit and stop_limit orders")
        if self.type in {OrderType.stop, OrderType.stop_limit} and self.stop_price is None:
            raise ValueError("stop_price is required for stop and stop_limit orders")
        return self


class OptionOrderRequest(BaseModel):
    mode: TradingMode
    contract_symbol: str = Field(min_length=8, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    side: OrderSide
    type: Literal["market", "limit"] = "market"
    time_in_force: Literal["day"] = "day"
    qty: int = Field(gt=0, le=1000)
    limit_price: float | None = Field(default=None, gt=0)
    position_intent: OptionPositionIntent | None = None
    live_confirmation_token: str | None = None

    @model_validator(mode="after")
    def validate_limit(self) -> "OptionOrderRequest":
        if self.type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        if self.position_intent is not None:
            expected_side = (
                OrderSide.buy
                if self.position_intent
                in {OptionPositionIntent.buy_to_open, OptionPositionIntent.buy_to_close}
                else OrderSide.sell
            )
            if self.side != expected_side:
                raise ValueError("side must match position_intent")
        return self


class OrderCancelRequest(BaseModel):
    mode: TradingMode
    live_confirmation_token: str | None = None


class OrderReplaceRequest(BaseModel):
    mode: TradingMode
    qty: float | None = Field(default=None, gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    live_confirmation_token: str | None = None

    @model_validator(mode="after")
    def validate_replacement(self) -> "OrderReplaceRequest":
        if self.qty is None and self.limit_price is None and self.stop_price is None:
            raise ValueError("Provide at least one replacement field")
        return self


class ForecastRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z.\-]+$")
    preset: Literal["short", "long"] = "short"
    timeframe: Literal["1Min", "5Min", "15Min", "1Hour", "1Day"] | None = None
    context: int | None = Field(default=None, ge=32, le=512)
    horizon: int | None = Field(default=None, ge=1, le=120)
    engine: Literal["kronos", "ensemble"] = "kronos"


class MoversScanRequest(BaseModel):
    refresh: bool = False
    limit: int = Field(default=50, ge=1, le=50)


class OrderPreviewRequest(BaseModel):
    kind: Literal["equity", "option"] = "equity"
    mode: TradingMode
    symbol: str | None = Field(default=None, max_length=16)
    contract_symbol: str | None = Field(default=None, max_length=32)
    side: OrderSide
    type: OrderType = OrderType.market
    qty: float | None = Field(default=None, gt=0)
    notional: float | None = Field(default=None, gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    position_intent: OptionPositionIntent | None = None

    @model_validator(mode="after")
    def validate_preview(self) -> "OrderPreviewRequest":
        if self.kind == "option":
            if not self.contract_symbol or self.qty is None:
                raise ValueError("contract_symbol and qty are required for option previews")
            if self.notional is not None or self.type not in {OrderType.market, OrderType.limit}:
                raise ValueError("Option previews support qty and market or limit orders only")
            if self.position_intent is not None:
                expected_side = (
                    OrderSide.buy
                    if self.position_intent
                    in {OptionPositionIntent.buy_to_open, OptionPositionIntent.buy_to_close}
                    else OrderSide.sell
                )
                if self.side != expected_side:
                    raise ValueError("side must match position_intent")
        else:
            if not self.symbol or (self.qty is None) == (self.notional is None):
                raise ValueError("symbol and exactly one of qty or notional are required")
            if self.position_intent is not None:
                raise ValueError("position_intent is only valid for option previews")
        if self.type == OrderType.limit and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        return self


class Bar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int | None = None
    vwap: float | None = None


class ProviderErrorBody(BaseModel):
    detail: str
    provider: str | None = None
    code: str | None = None


JsonDict = dict[str, Any]
