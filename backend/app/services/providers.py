from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import httpx
from cachetools import TTLCache

from app.config import Settings

_FILL_PAGE_SIZE = 100
_FILL_MAX_PAGES = 50
_QTY_EPS = 1e-12


def fifo_realized_pl(fills: list[dict[str, Any]]) -> float:
    """Compute closed-trade realized P/L from FILL activities using FIFO lots.

    Each fill needs ``symbol``, ``side`` (buy/sell), ``qty``, and ``price``.
    Fills must be ordered oldest-first. Open lots are ignored (unrealized).
    """
    lots: dict[str, deque[tuple[float, float]]] = defaultdict(deque)
    realized = 0.0

    for fill in fills:
        symbol = str(fill.get("symbol") or "").upper()
        if not symbol:
            continue
        side = str(fill.get("side") or "").lower()
        try:
            qty = abs(float(fill.get("qty") or 0))
            price = float(fill.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        remaining = qty if side == "buy" else -qty if side == "sell" else 0.0
        if remaining == 0:
            continue

        book = lots[symbol]
        while abs(remaining) > _QTY_EPS and book and (
            (remaining > 0 and book[0][0] < 0) or (remaining < 0 and book[0][0] > 0)
        ):
            lot_qty, lot_price = book[0]
            if remaining > 0:
                close_qty = min(remaining, -lot_qty)
                realized += (lot_price - price) * close_qty
                lot_qty += close_qty
                remaining -= close_qty
            else:
                close_qty = min(-remaining, lot_qty)
                realized += (price - lot_price) * close_qty
                lot_qty -= close_qty
                remaining += close_qty
            if abs(lot_qty) <= _QTY_EPS:
                book.popleft()
            else:
                book[0] = (lot_qty, lot_price)

        if abs(remaining) > _QTY_EPS:
            book.append((remaining, price))

    return realized


class ProviderUnavailable(RuntimeError):
    def __init__(self, provider: str, message: str):
        super().__init__(message)
        self.provider = provider


SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "alphabet": ("GOOGL", "GOOG"),
    "facebook": ("META",),
    "fb": ("META",),
    "google": ("GOOGL", "GOOG"),
    "meta": ("META",),
}

SEARCH_RESULT_LIMIT = 40
_OCC_OPTION_SYMBOL = re.compile(r"^([A-Z]{1,6})\d{6}[CP]\d{8}$")


def option_underlying_symbol(contract: Any, contract_symbol: str) -> str | None:
    """Resolve the underlying across Alpaca SDK model versions, then OCC as fallback."""
    if isinstance(contract, dict):
        direct = contract.get("underlying_symbol")
        nested = contract.get("underlying_asset")
    else:
        direct = getattr(contract, "underlying_symbol", None)
        nested = getattr(contract, "underlying_asset", None)
    if direct:
        return str(direct).upper()
    if nested:
        nested_symbol = (
            nested.get("symbol") if isinstance(nested, dict) else getattr(nested, "symbol", None)
        )
        if nested_symbol:
            return str(nested_symbol).upper()
    match = _OCC_OPTION_SYMBOL.fullmatch(contract_symbol.upper())
    return match.group(1) if match else None


def rank_search_results(query: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    needle = query.strip().casefold()
    aliases = {symbol.upper() for symbol in SEARCH_ALIASES.get(needle, ())}

    def key(item: dict[str, Any]) -> tuple:
        symbol = str(item.get("symbol") or "")
        name = str(item.get("name") or "")
        symbol_upper = symbol.upper()
        symbol_cf = symbol.casefold()
        name_cf = name.casefold()
        if symbol_upper in aliases or symbol_cf == needle:
            bucket = 0
        elif symbol_cf.startswith(needle):
            bucket = 1
        elif name_cf.startswith(needle):
            bucket = 2
        else:
            bucket = 3
        extra = symbol.count(".") + symbol.count("/") + symbol.count("-")
        tradable_penalty = 0 if item.get("tradable", True) else 1
        return (bucket, extra, tradable_penalty, len(symbol_upper), symbol_upper)

    return sorted(items, key=key)


_POSITIVE_NEWS = re.compile(
    r"\b("
    r"beat|beats|beating|upgrade|upgraded|upgrades|surge|surges|surged|"
    r"rally|rallies|rallied|soar|soars|soared|jump|jumps|jumped|"
    r"gain|gains|gained|profit|profits|profitable|growth|bullish|"
    r"outperform|outperforms|outperformed|exceed|exceeds|exceeded|"
    r"raised|raises|approval|approved|breakthrough|dividend|expansion|"
    r"optimistic|boost|boosts|boosted|record(?:s)?|all-time high"
    r")\b",
    re.IGNORECASE,
)
_NEGATIVE_NEWS = re.compile(
    r"\b("
    r"miss|misses|missed|downgrade|downgraded|downgrades|plunge|plunges|plunged|"
    r"slump|slumps|slumped|drop|drops|dropped|loss|losses|lawsuit|sued|"
    r"probe|investigation|fraud|weak|weakness|bearish|warning|warns|warned|"
    r"layoff|layoffs|bankrupt|bankruptcy|recall|recalled|delay|delayed|"
    r"reject|rejected|decline|declines|declined|crash|crashed|sell-?off|"
    r"scandal|fined|disappoint|disappoints|disappointed|tumble|tumbles|tumbled|"
    r"sinks|sank|worst"
    r")\b",
    re.IGNORECASE,
)


def classify_article_sentiment(headline: str, summary: str = "") -> str:
    text = f"{headline} {summary}".strip()
    if not text:
        return "neutral"
    positive = len(_POSITIVE_NEWS.findall(text))
    negative = len(_NEGATIVE_NEWS.findall(text))
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def article_sentiment(data: dict[str, Any], headline: str = "", summary: str = "") -> str:
    raw = str(data.get("sentiment") or "").casefold()
    if raw in {"positive", "bullish"}:
        return "positive"
    if raw in {"negative", "bearish"}:
        return "negative"
    if raw == "neutral":
        return "neutral"
    return classify_article_sentiment(headline or str(data.get("headline") or ""), summary or str(data.get("summary") or ""))


def _unix_to_iso(value: Any) -> Any:
    if isinstance(value, (int, float)) and value > 1_000_000_000:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return value


def normalize_news(response: Any, symbol: str, limit: int) -> list[dict[str, Any]]:
    ticker = symbol.upper()
    payload = getattr(response, "news", None)
    if payload is None:
        payload = getattr(response, "data", response)
    payload = jsonable(payload)
    if isinstance(payload, dict):
        payload = payload.get("news") or payload.get("data") or []
    if not isinstance(payload, list):
        return []

    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload:
        data = jsonable(item)
        if not isinstance(data, dict):
            continue
        headline = data.get("headline") or data.get("title")
        if not headline:
            continue
        symbols = data.get("symbols") or data.get("related") or []
        if isinstance(symbols, str):
            symbols = [part.strip() for part in symbols.split(",") if part.strip()]
        mentioned = {str(entry).upper() for entry in symbols if entry}
        if mentioned and ticker not in mentioned:
            continue
        url = str(data.get("url") or data.get("link") or "")
        key = (url or str(headline)).casefold()
        if key in seen:
            continue
        seen.add(key)
        summary = data.get("summary") or ""
        articles.append(
            {
                "id": data.get("id"),
                "headline": headline,
                "summary": summary,
                "source": data.get("source") or data.get("author") or "",
                "url": url,
                "created_at": _unix_to_iso(
                    data.get("created_at") or data.get("updated_at") or data.get("datetime")
                ),
                "symbols": list(mentioned) or [ticker],
                "sentiment": article_sentiment(data, str(headline), str(summary)),
            }
        )
        if len(articles) >= limit:
            break
    return articles


def merge_news(*groups: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            key = str(item.get("url") or item.get("headline") or "").casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append({**item, "sentiment": article_sentiment(item)})
            if len(merged) >= limit:
                return merged
    return merged


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return {k: jsonable(v) for k, v in value.model_dump().items()}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return str(value)


class FinnhubService:
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.api_key = settings.finnhub_api_key
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=512, ttl=300)

    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderUnavailable("finnhub", "FINNHUB_API_KEY is not configured")

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        self._require_key()
        cache_key = f"{path}:{sorted(params.items())}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        request_params = {**params, "token": self.api_key}
        response = await self.client.get(f"{self.BASE_URL}{path}", params=request_params)
        response.raise_for_status()
        payload = response.json()
        self._cache[cache_key] = payload
        return payload

    async def search(self, query: str) -> list[dict[str, Any]]:
        payload = await self._get("/search", {"q": query})
        return [
            {
                "symbol": item.get("symbol"),
                "name": item.get("description"),
                "type": item.get("type"),
                "display_symbol": item.get("displaySymbol"),
            }
            for item in payload.get("result", [])
            if item.get("symbol")
        ]

    async def company_news(self, symbol: str, limit: int = 8) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        payload = await self._get(
            "/company-news",
            {
                "symbol": symbol.upper(),
                "from": (today - timedelta(days=30)).isoformat(),
                "to": today.isoformat(),
            },
        )
        return normalize_news(payload if isinstance(payload, list) else [], symbol, limit)

    async def fundamentals(self, symbol: str) -> dict[str, float | None]:
        metric = await self._get("/stock/metric", {"symbol": symbol, "metric": "all"})
        values = metric.get("metric") or {}

        def number(*names: str) -> float | None:
            for name in names:
                value = values.get(name)
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return None
            return None

        return {
            "pe_ratio": number("peBasicExclExtraTTM", "peTTM"),
            # Finnhub reports market capitalization in millions of the quote currency.
            "market_cap": (
                value * 1_000_000
                if (value := number("marketCapitalization")) is not None
                else None
            ),
            "dividend_yield": (
                value / 100.0
                if (
                    value := number(
                        "dividendYieldIndicatedAnnual",
                        "dividendYieldTTM",
                    )
                )
                is not None
                else None
            ),
            "eps": number("epsBasicExclExtraItemsTTM", "epsTTM"),
        }

    async def news_sentiment(self, symbol: str) -> dict[str, Any]:
        payload = await self._get("/news-sentiment", {"symbol": symbol.upper()})
        sentiment = payload.get("sentiment") if isinstance(payload, dict) else {}
        if not isinstance(sentiment, dict):
            sentiment = {}

        def ratio(value: Any) -> float | None:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                return None
            if not (parsed == parsed):  # NaN
                return None
            return parsed / 100.0 if parsed > 1 else parsed

        bullish = ratio(sentiment.get("bullishPercent"))
        bearish = ratio(sentiment.get("bearishPercent"))
        score = ratio(payload.get("companyNewsScore")) if isinstance(payload, dict) else None
        if bullish is None or bearish is None:
            label = "neutral"
        elif bullish - bearish > 0.10:
            label = "bullish"
        elif bearish - bullish > 0.10:
            label = "bearish"
        else:
            label = "neutral"
        return {
            "label": label,
            "bullish_percent": bullish,
            "bearish_percent": bearish,
            "score": score,
        }


class AlpacaService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._trading_clients: dict[str, Any] = {}
        self._stock_client: Any = None
        self._option_client: Any = None
        self._asset_cache: TTLCache[str, Any] = TTLCache(maxsize=4, ttl=300)

    def _credentials(self, mode: str) -> tuple[str, str]:
        if mode == "paper":
            key, secret = self.settings.alpaca_paper_key, self.settings.alpaca_paper_secret
        else:
            key, secret = self.settings.alpaca_live_key, self.settings.alpaca_live_secret
        if not key or not secret:
            raise ProviderUnavailable("alpaca", f"Alpaca {mode} credentials are not configured")
        return key, secret

    def _trading(self, mode: str) -> Any:
        key, secret = self._credentials(mode)
        if mode not in self._trading_clients:
            from alpaca.trading.client import TradingClient

            self._trading_clients[mode] = TradingClient(key, secret, paper=(mode == "paper"))
        return self._trading_clients[mode]

    def _stock_data(self) -> Any:
        key, secret = self._credentials(self.settings.alpaca_data_credentials_mode)
        if self._stock_client is None:
            from alpaca.data.historical import StockHistoricalDataClient

            self._stock_client = StockHistoricalDataClient(key, secret)
        return self._stock_client

    def _option_data(self) -> Any:
        key, secret = self._credentials(self.settings.alpaca_data_credentials_mode)
        if self._option_client is None:
            from alpaca.data.historical.option import OptionHistoricalDataClient

            self._option_client = OptionHistoricalDataClient(key, secret)
        return self._option_client

    def _stock_feed(self) -> Any:
        from alpaca.data.enums import DataFeed

        return DataFeed(self.settings.alpaca_data_feed)

    def get_asset(self, symbol: str, mode: str = "paper") -> Any:
        try:
            return self._trading(mode).get_asset(symbol.upper())
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ValueError(f"Unknown asset: {symbol}") from exc

    def search_assets(self, query: str, mode: str = "paper") -> list[dict[str, Any]]:
        from alpaca.trading.enums import AssetClass, AssetStatus
        from alpaca.trading.requests import GetAssetsRequest

        cache_key = f"assets:{mode}"
        if cache_key not in self._asset_cache:
            request = GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
            self._asset_cache[cache_key] = self._trading(mode).get_all_assets(request)
        needle = query.casefold()
        aliases = {symbol.upper() for symbol in SEARCH_ALIASES.get(needle, ())}
        results = []
        for asset in self._asset_cache[cache_key]:
            symbol = getattr(asset, "symbol", "")
            name = getattr(asset, "name", "")
            if (
                symbol.upper() in aliases
                or needle in symbol.casefold()
                or needle in name.casefold()
            ):
                results.append(
                    {
                        "symbol": symbol,
                        "name": name,
                        "exchange": jsonable(getattr(asset, "exchange", None)),
                        "tradable": bool(getattr(asset, "tradable", False)),
                    }
                )
        return rank_search_results(query, results)[:SEARCH_RESULT_LIMIT]

    def snapshot(self, symbol: str) -> dict[str, Any]:
        from alpaca.data.requests import StockSnapshotRequest

        raw = self._stock_data().get_stock_snapshot(
            StockSnapshotRequest(
                symbol_or_symbols=symbol.upper(),
                feed=self._stock_feed(),
            )
        )
        snapshot = raw.get(symbol.upper()) if isinstance(raw, dict) else raw
        latest_trade = getattr(snapshot, "latest_trade", None)
        latest_quote = getattr(snapshot, "latest_quote", None)
        daily = getattr(snapshot, "daily_bar", None)
        previous = getattr(snapshot, "previous_daily_bar", None)
        timestamp = getattr(latest_trade, "timestamp", None) or getattr(daily, "timestamp", None)
        try:
            asset = self.get_asset(symbol)
        except (ProviderUnavailable, ValueError):
            asset = None
        return {
            "symbol": symbol.upper(),
            "name": getattr(asset, "name", None),
            "exchange": jsonable(getattr(asset, "exchange", None)),
            "current_price": getattr(latest_trade, "price", None),
            "bid": getattr(latest_quote, "bid_price", None),
            "ask": getattr(latest_quote, "ask_price", None),
            "timestamp": jsonable(timestamp),
            "session": self._session(timestamp),
            "daily": self._bar_dict(daily),
            "previous_daily": self._bar_dict(previous),
        }

    def market_clock(self, mode: str = "paper") -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        try:
            clock = self._trading(mode).get_clock()
        except ProviderUnavailable:
            session = self._session(now)
            return {
                "is_open": session == "regular",
                "session": session,
                "timestamp": jsonable(now),
                "next_open": None,
                "next_close": None,
            }
        now = getattr(clock, "timestamp", None) or now
        is_open = bool(getattr(clock, "is_open", False))
        inferred = self._session(now)
        if is_open:
            session = "regular"
        elif inferred == "regular":
            session = "closed"
        else:
            session = inferred
        return {
            "is_open": is_open,
            "session": session,
            "timestamp": jsonable(now),
            "next_open": jsonable(getattr(clock, "next_open", None)),
            "next_close": jsonable(getattr(clock, "next_close", None)),
        }

    @staticmethod
    def _session(timestamp: datetime | None) -> str:
        if timestamp is None:
            return "unknown"
        try:
            from zoneinfo import ZoneInfo

            eastern = timestamp.astimezone(ZoneInfo("America/New_York"))
            minutes = eastern.hour * 60 + eastern.minute
            if eastern.weekday() >= 5:
                return "closed"
            if 570 <= minutes < 960:
                return "regular"
            if 240 <= minutes < 570:
                return "pre_market"
            if 960 <= minutes < 1200:
                return "after_hours"
            return "closed"
        except Exception:
            return "unknown"

    @staticmethod
    def _bar_dict(bar: Any) -> dict[str, Any] | None:
        if bar is None:
            return None
        return {
            "timestamp": jsonable(getattr(bar, "timestamp", None)),
            "open": getattr(bar, "open", None),
            "high": getattr(bar, "high", None),
            "low": getattr(bar, "low", None),
            "close": getattr(bar, "close", None),
            "volume": getattr(bar, "volume", None),
            "trade_count": getattr(bar, "trade_count", None),
            "vwap": getattr(bar, "vwap", None),
        }

    def bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        from alpaca.common.enums import Sort
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        mapping = {
            "1Min": TimeFrame.Minute,
            "5Min": TimeFrame(5, TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
        }
        end = end or datetime.now(timezone.utc)
        if start is None:
            if timeframe == "1Day":
                history_days = max(30, limit * 2)
            elif timeframe == "1Hour":
                history_days = max(7, limit // 5)
            else:
                history_days = max(7, limit // 48)
            start = end - timedelta(days=history_days)
        result = self._stock_data().get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=mapping[timeframe],
                start=start,
                end=end,
                limit=limit,
                feed=self._stock_feed(),
                sort=Sort.DESC,
            )
        )
        data = getattr(result, "data", result)
        items = data.get(symbol.upper(), []) if isinstance(data, dict) else []
        bars = [self._bar_dict(bar) for bar in items]
        return sorted(
            (bar for bar in bars if bar is not None),
            key=lambda bar: str(bar.get("timestamp") or ""),
        )

    def news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest

        key, secret = self._credentials(self.settings.alpaca_data_credentials_mode)
        response = NewsClient(key, secret).get_news(
            NewsRequest(symbols=symbol.upper(), limit=max(limit, 10), sort="desc")
        )
        return normalize_news(response, symbol, limit)

    def account(self, mode: str) -> dict[str, Any]:
        from app.services.risk import account_risk_status

        raw = self._trading(mode).get_account()
        payload = jsonable(raw)
        if not isinstance(payload, dict):
            payload = {}
        try:
            positions = jsonable(self._trading(mode).get_all_positions())
        except Exception:
            positions = []
        if not isinstance(positions, list):
            positions = []
        payload["risk"] = account_risk_status(raw, positions, self.settings)
        return payload

    def positions(self, mode: str) -> list[dict[str, Any]]:
        return jsonable(self._trading(mode).get_all_positions())

    def _fill_activities(self, mode: str) -> list[dict[str, Any]]:
        """Paginate Alpaca FILL activities (newest-first pages) into a flat list."""
        client = self._trading(mode)
        fills: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(_FILL_MAX_PAGES):
            params: dict[str, Any] = {
                "activity_types": "FILL",
                "direction": "desc",
                "page_size": _FILL_PAGE_SIZE,
            }
            if page_token:
                params["page_token"] = page_token
            raw = client.get("/account/activities", params)
            page = jsonable(raw)
            if not isinstance(page, list):
                page = []
            if not page:
                break
            for item in page:
                if not isinstance(item, dict):
                    continue
                activity_type = str(item.get("activity_type") or item.get("activityType") or "")
                if activity_type and activity_type.upper() != "FILL":
                    continue
                fills.append(item)
            if len(page) < _FILL_PAGE_SIZE:
                break
            last_id = page[-1].get("id") if isinstance(page[-1], dict) else None
            if not last_id or last_id == page_token:
                break
            page_token = str(last_id)
        return fills

    def realized_pl(self, mode: str) -> dict[str, Any]:
        fills = self._fill_activities(mode)

        def sort_key(item: dict[str, Any]) -> str:
            return str(
                item.get("transaction_time")
                or item.get("transactionTime")
                or item.get("date")
                or item.get("id")
                or ""
            )

        ordered = sorted(fills, key=sort_key)
        normalized: list[dict[str, Any]] = []
        for item in ordered:
            side = item.get("side")
            if hasattr(side, "value"):
                side = side.value
            normalized.append(
                {
                    "symbol": item.get("symbol"),
                    "side": side,
                    "qty": item.get("qty"),
                    "price": item.get("price"),
                }
            )
        return {
            "realized_pl": round(fifo_realized_pl(normalized), 6),
            "fill_count": len(normalized),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    def orders(self, mode: str, status: str, limit: int) -> list[dict[str, Any]]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        return jsonable(
            self._trading(mode).get_orders(
                GetOrdersRequest(status=QueryOrderStatus(status), limit=limit)
            )
        )

    def option_contracts(
        self,
        underlying: str,
        expiration: str | None,
        contract_type: str | None,
        limit: int,
        mode: str,
    ) -> list[dict[str, Any]]:
        from alpaca.trading.enums import ContractType
        from alpaca.trading.requests import GetOptionContractsRequest

        kwargs: dict[str, Any] = {
            "underlying_symbols": [underlying.upper()],
            "limit": limit,
        }
        if expiration:
            kwargs["expiration_date"] = expiration
        if contract_type:
            kwargs["type"] = ContractType(contract_type)
        response = self._trading(mode).get_option_contracts(GetOptionContractsRequest(**kwargs))
        return jsonable(getattr(response, "option_contracts", response))

    def option_chain(
        self,
        underlying: str,
        expiration: str | None = None,
        contract_type: str | None = None,
    ) -> dict[str, Any]:
        from alpaca.trading.enums import ContractType
        from alpaca.data.requests import OptionChainRequest

        kwargs: dict[str, Any] = {"underlying_symbol": underlying.upper()}
        if expiration:
            kwargs["expiration_date"] = expiration
        if contract_type:
            kwargs["type"] = ContractType(contract_type)
        response = self._option_data().get_option_chain(
            OptionChainRequest(**kwargs)
        )
        return jsonable(response)

    def option_snapshot(
        self, contract_symbol: str, underlying: str | None = None
    ) -> dict[str, Any]:
        """Return quote fields in the shape consumed by option risk checks."""
        from alpaca.data.requests import OptionSnapshotRequest

        ticker = contract_symbol.upper()
        response = self._option_data().get_option_snapshot(
            OptionSnapshotRequest(symbol_or_symbols=ticker)
        )
        payload = jsonable(response)
        item = payload.get(ticker, {}) if isinstance(payload, dict) else {}
        quote = item.get("latest_quote") or {}
        trade = item.get("latest_trade") or {}
        daily = item.get("daily_bar") or {}
        bid = quote.get("bid_price")
        ask = quote.get("ask_price")
        return {
            "symbol": (underlying or ticker).upper(),
            "contract_symbol": ticker,
            "bid": bid,
            "ask": ask,
            "current_price": ask or trade.get("price") or bid,
            "daily": daily,
        }

    def _positions(self, mode: str) -> list[Any]:
        try:
            payload = jsonable(self._trading(mode).get_all_positions())
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def _ensure_order_risk(self, order: Any, *, option: bool = False, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.services.risk import check_order_risk

        mode = order.mode.value if hasattr(order.mode, "value") else str(order.mode)
        account = self._trading(mode).get_account()
        symbol = getattr(order, "symbol", None) or (snapshot or {}).get("symbol")
        if snapshot is None and symbol and not option:
            try:
                snapshot = self.snapshot(symbol)
            except Exception:
                snapshot = {}
        if symbol and snapshot is not None and "average_daily_volume" not in snapshot:
            try:
                end = datetime.now(timezone.utc)
                history = self.bars(
                    symbol,
                    "1Day",
                    end - timedelta(days=45),
                    end,
                    30,
                )
                volumes = [
                    float(bar["volume"])
                    for bar in history
                    if bar.get("volume") is not None and float(bar["volume"]) >= 0
                ]
                if volumes:
                    snapshot["average_daily_volume"] = sum(volumes) / len(volumes)
            except Exception:
                pass
        return check_order_risk(
            order,
            account=account,
            positions=self._positions(mode),
            snapshot=snapshot or {},
            settings=self.settings,
            option=option,
        )

    def preview_order(self, request: Any) -> dict[str, Any]:
        kind = getattr(request, "kind", "equity")
        if kind == "option":
            order = type("Preview", (), {})()
            order.mode = request.mode
            order.side = request.side
            order.type = request.type
            order.qty = request.qty
            order.notional = None
            order.limit_price = request.limit_price
            order.stop_price = None
            order.contract_symbol = request.contract_symbol
            order.position_intent = request.position_intent
            snapshot: dict[str, Any] = {}
            try:
                contract = self._trading(request.mode.value).get_option_contract(
                    request.contract_symbol.upper()
                )
                underlying = option_underlying_symbol(contract, request.contract_symbol)
            except ProviderUnavailable:
                raise
            except Exception as exc:
                raise ValueError(f"Unknown option contract: {request.contract_symbol}") from exc
            order.symbol = underlying or request.symbol
            try:
                snapshot = self.option_snapshot(request.contract_symbol, order.symbol)
            except ProviderUnavailable:
                raise
            except Exception:
                snapshot = {"symbol": order.symbol or request.contract_symbol}
            return self._ensure_order_risk(order, option=True, snapshot=snapshot)
        order = type("Preview", (), {})()
        order.mode = request.mode
        order.side = request.side
        order.type = request.type
        order.qty = request.qty
        order.notional = request.notional
        order.limit_price = request.limit_price
        order.stop_price = None
        order.symbol = request.symbol
        order.contract_symbol = None
        order.position_intent = None
        return self._ensure_order_risk(order, option=False)

    def submit_equity_order(self, order: Any) -> dict[str, Any]:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopLimitOrderRequest,
            StopOrderRequest,
        )

        asset = self.get_asset(order.symbol, order.mode.value)
        if not getattr(asset, "tradable", False):
            raise ValueError(f"{order.symbol.upper()} is not tradable")
        self._ensure_order_risk(order, option=False)
        common = {
            "symbol": order.symbol.upper(),
            "side": OrderSide(order.side.value),
            "time_in_force": TimeInForce(order.time_in_force.value),
            "qty": order.qty,
            "notional": order.notional,
        }
        common = {k: v for k, v in common.items() if v is not None}
        request_cls: Any = MarketOrderRequest
        if order.type.value == "limit":
            request_cls, common["limit_price"] = LimitOrderRequest, order.limit_price
        elif order.type.value == "stop":
            request_cls, common["stop_price"] = StopOrderRequest, order.stop_price
        elif order.type.value == "stop_limit":
            request_cls = StopLimitOrderRequest
            common.update(limit_price=order.limit_price, stop_price=order.stop_price)
        common["extended_hours"] = order.extended_hours
        return jsonable(self._trading(order.mode.value).submit_order(request_cls(**common)))

    def submit_option_order(self, order: Any) -> dict[str, Any]:
        from alpaca.trading.enums import OrderSide, PositionIntent, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        try:
            contract = self._trading(order.mode.value).get_option_contract(
                order.contract_symbol.upper()
            )
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ValueError(f"Unknown option contract: {order.contract_symbol}") from exc
        if not getattr(contract, "tradable", False):
            raise ValueError(f"{order.contract_symbol} is not tradable")
        underlying = option_underlying_symbol(contract, order.contract_symbol)
        try:
            snapshot = self.option_snapshot(order.contract_symbol, underlying)
        except ProviderUnavailable:
            raise
        except Exception:
            snapshot = {"symbol": str(underlying or order.contract_symbol)}
        self._ensure_order_risk(order, option=True, snapshot=snapshot)
        intent_value = (
            order.position_intent.value
            if getattr(order, "position_intent", None) is not None
            else ("buy_to_open" if order.side.value == "buy" else "sell_to_close")
        )
        common = {
            "symbol": order.contract_symbol.upper(),
            "qty": order.qty,
            "side": OrderSide(order.side.value),
            "time_in_force": TimeInForce.DAY,
            "position_intent": PositionIntent(intent_value),
        }
        request = (
            LimitOrderRequest(**common, limit_price=order.limit_price)
            if order.type == "limit"
            else MarketOrderRequest(**common)
        )
        return jsonable(self._trading(order.mode.value).submit_order(request))

    def cancel_order(self, order_id: str, mode: str) -> dict[str, Any]:
        self._trading(mode).cancel_order_by_id(order_id)
        return {"id": order_id, "status": "cancel_requested"}

    def replace_order(self, order_id: str, replacement: Any) -> dict[str, Any]:
        from alpaca.trading.requests import ReplaceOrderRequest

        client = self._trading(replacement.mode.value)
        existing = client.get_order_by_id(order_id)
        symbol = str(getattr(existing, "symbol", "") or "").upper()
        option = bool(_OCC_OPTION_SYMBOL.fullmatch(symbol))
        candidate = type("ReplacementRiskOrder", (), {})()
        candidate.mode = replacement.mode
        candidate.side = getattr(existing, "side", None)
        candidate.type = getattr(existing, "type", "limit")
        candidate.qty = replacement.qty or getattr(existing, "qty", None)
        candidate.notional = getattr(existing, "notional", None)
        candidate.limit_price = replacement.limit_price or getattr(existing, "limit_price", None)
        candidate.stop_price = replacement.stop_price or getattr(existing, "stop_price", None)
        candidate.position_intent = getattr(existing, "position_intent", None)
        candidate.contract_symbol = symbol if option else None
        candidate.symbol = symbol
        snapshot: dict[str, Any] | None = None
        if option:
            contract = client.get_option_contract(symbol)
            underlying = option_underlying_symbol(contract, symbol)
            candidate.symbol = underlying or symbol
            if underlying:
                try:
                    snapshot = self.snapshot(underlying)
                except Exception:
                    snapshot = {"symbol": underlying}
        self._ensure_order_risk(candidate, option=option, snapshot=snapshot)
        payload = {
            "qty": replacement.qty,
            "limit_price": replacement.limit_price,
            "stop_price": replacement.stop_price,
        }
        request = ReplaceOrderRequest(**{key: value for key, value in payload.items() if value is not None})
        return jsonable(client.replace_order_by_id(order_id, request))

    def _data_headers(self) -> dict[str, str]:
        key, secret = self._credentials(self.settings.alpaca_data_credentials_mode)
        return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    def _screener(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                f"https://data.alpaca.markets/v1beta1/screener/stocks/{path}",
                params=params,
                headers=self._data_headers(),
            )
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("alpaca", f"Screener {path} failed: {exc}") from exc
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def most_actives(self, top: int = 50) -> list[dict[str, Any]]:
        payload = self._screener("most-actives", {"by": "volume", "top": top})
        rows = payload.get("most_actives") or payload.get("actives") or []
        results: list[dict[str, Any]] = []
        for item in rows:
            data = jsonable(item)
            if not isinstance(data, dict) or not data.get("symbol"):
                continue
            results.append(
                {
                    "symbol": str(data["symbol"]).upper(),
                    "volume": data.get("volume"),
                    "trade_count": data.get("trade_count"),
                }
            )
        return results

    def movers(self, top: int = 20) -> dict[str, list[dict[str, Any]]]:
        payload = self._screener("movers", {"top": top, "market_type": "stocks"})

        def rows(key: str) -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            for item in payload.get(key) or []:
                data = jsonable(item)
                if not isinstance(data, dict) or not data.get("symbol"):
                    continue
                results.append(
                    {
                        "symbol": str(data["symbol"]).upper(),
                        "percent_change": data.get("percent_change"),
                        "change": data.get("change"),
                        "price": data.get("price"),
                    }
                )
            return results

        return {"gainers": rows("gainers"), "losers": rows("losers")}

    def snapshots_many(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        from alpaca.data.requests import StockSnapshotRequest

        unique = [symbol.upper() for symbol in dict.fromkeys(symbols) if symbol]
        if not unique:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for index in range(0, len(unique), 50):
            chunk = unique[index : index + 50]
            raw = self._stock_data().get_stock_snapshot(
                StockSnapshotRequest(symbol_or_symbols=chunk, feed=self._stock_feed())
            )
            payload = raw if isinstance(raw, dict) else {}
            for symbol in chunk:
                snapshot = payload.get(symbol)
                if snapshot is None:
                    continue
                latest_trade = getattr(snapshot, "latest_trade", None)
                daily = getattr(snapshot, "daily_bar", None)
                previous = getattr(snapshot, "previous_daily_bar", None)
                timestamp = getattr(latest_trade, "timestamp", None) or getattr(
                    daily, "timestamp", None
                )
                result[symbol] = {
                    "symbol": symbol,
                    "current_price": getattr(latest_trade, "price", None),
                    "timestamp": jsonable(timestamp),
                    "daily": self._bar_dict(daily),
                    "previous_daily": self._bar_dict(previous),
                }
        return result

    def bars_many(
        self,
        symbols: list[str],
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> dict[str, list[dict[str, Any]]]:
        from alpaca.common.enums import Sort
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        mapping = {
            "1Min": TimeFrame.Minute,
            "5Min": TimeFrame(5, TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
        }
        unique = [symbol.upper() for symbol in dict.fromkeys(symbols) if symbol]
        if not unique:
            return {}
        end = end or datetime.now(timezone.utc)
        if start is None:
            if timeframe == "1Day":
                history_days = max(30, limit * 2)
            elif timeframe == "1Hour":
                history_days = max(7, limit // 5)
            else:
                history_days = max(7, limit // 48)
            start = end - timedelta(days=history_days)
        collected: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in unique}
        for index in range(0, len(unique), 40):
            chunk = unique[index : index + 40]
            result = self._stock_data().get_stock_bars(
                StockBarsRequest(
                    symbol_or_symbols=chunk,
                    timeframe=mapping[timeframe],
                    start=start,
                    end=end,
                    limit=limit,
                    feed=self._stock_feed(),
                    sort=Sort.DESC,
                )
            )
            data = getattr(result, "data", result)
            payload = data if isinstance(data, dict) else {}
            for symbol in chunk:
                bars = [self._bar_dict(bar) for bar in payload.get(symbol, [])]
                collected[symbol] = sorted(
                    (bar for bar in bars if bar is not None),
                    key=lambda bar: str(bar.get("timestamp") or ""),
                )
        return collected
