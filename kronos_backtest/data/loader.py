"""Historical market data access with an explicit as-of boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from kronos_backtest.data.validator import (
    timestamps_of,
    to_timestamp,
    validate_context,
    validate_sorted_ohlcv,
)
from kronos_backtest.exceptions import InsufficientHistoryError, LookAheadBiasError
from kronos_backtest.types import Bar


COLUMN_ALIASES = {
    "date": "timestamp",
    "datetime": "timestamp",
    "time": "timestamp",
    "timestamps": "timestamp",
    "vol": "volume",
    "amt": "amount",
    "ticker": "symbol",
    "code": "symbol",
}


def _normalize_frame(frame: pd.DataFrame, default_symbol: str) -> pd.DataFrame:
    data = frame.copy()
    rename = {src: dst for src, dst in COLUMN_ALIASES.items() if src in data.columns and dst not in data.columns}
    if rename:
        data = data.rename(columns=rename)
    if "timestamp" not in data.columns:
        data = data.reset_index()
        if "timestamp" not in data.columns:
            first = data.columns[0]
            data = data.rename(columns={first: "timestamp"})
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    if getattr(data["timestamp"].dt, "tz", None) is not None:
        data["timestamp"] = data["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
    if "symbol" not in data.columns:
        data["symbol"] = default_symbol
    data["symbol"] = data["symbol"].astype(str)
    if "volume" not in data.columns:
        data["volume"] = 0.0
    if "amount" not in data.columns:
        data["amount"] = data["volume"] * data[["open", "high", "low", "close"]].mean(axis=1)
    if "returns" not in data.columns:
        data["returns"] = data.groupby("symbol")["close"].pct_change().fillna(0.0)
    data = data.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return data


def frame_to_bar(row: pd.Series) -> Bar:
    extras = {
        key: value
        for key, value in row.items()
        if key
        not in {
            "timestamp",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "bid",
            "ask",
        }
    }
    return Bar(
        timestamp=to_timestamp(row["timestamp"]),
        symbol=str(row["symbol"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume") or 0.0),
        amount=float(row.get("amount") or 0.0),
        bid=None if pd.isna(row.get("bid")) else float(row["bid"]) if "bid" in row else None,
        ask=None if pd.isna(row.get("ask")) else float(row["ask"]) if "ask" in row else None,
        extras=extras,
    )


class MarketData:
    """In-memory OHLCV store that can only be queried as-of a timestamp."""

    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        default_symbol: str = "ASSET",
        corporate_actions: pd.DataFrame | None = None,
        dataset_version: str = "",
    ) -> None:
        self._frame = _normalize_frame(frame, default_symbol)
        for symbol, group in self._frame.groupby("symbol", sort=False):
            validate_sorted_ohlcv(group.set_index("timestamp"))
        self._corporate_actions = (
            _normalize_frame(corporate_actions, default_symbol)
            if corporate_actions is not None and not corporate_actions.empty
            else pd.DataFrame(columns=["timestamp", "symbol"])
        )
        self.dataset_version = dataset_version
        self.default_symbol = str(self._frame["symbol"].iloc[0])

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        default_symbol: str = "ASSET",
        corporate_actions_path: str | Path | None = None,
    ) -> "MarketData":
        frame = pd.read_csv(path)
        actions = pd.read_csv(corporate_actions_path) if corporate_actions_path else None
        version = f"sha256:{_file_fingerprint(path)}"
        return cls(frame, default_symbol=default_symbol, corporate_actions=actions, dataset_version=version)

    @property
    def frame(self) -> pd.DataFrame:
        return self._frame.copy()

    @property
    def symbols(self) -> list[str]:
        return list(dict.fromkeys(self._frame["symbol"].tolist()))

    def index(self, symbol: str | None = None) -> pd.DatetimeIndex:
        data = self._frame if symbol is None else self._frame[self._frame["symbol"] == symbol]
        return pd.DatetimeIndex(data["timestamp"].tolist())

    def bars(self, symbol: str | None = None) -> list[Bar]:
        data = self._frame if symbol is None else self._frame[self._frame["symbol"] == symbol]
        return [frame_to_bar(row) for _, row in data.iterrows()]

    def get_bar(self, timestamp: pd.Timestamp, symbol: str | None = None) -> Bar:
        symbol = symbol or self.default_symbol
        current = to_timestamp(timestamp)
        match = self._frame[
            (self._frame["symbol"] == symbol) & (self._frame["timestamp"] == current)
        ]
        if match.empty:
            raise KeyError(f"No bar for {symbol} at {current}")
        return frame_to_bar(match.iloc[0])

    def get_history(
        self,
        current_timestamp: pd.Timestamp | str,
        *,
        symbol: str | None = None,
        lookback: int | None = None,
    ) -> pd.DataFrame:
        """Return rows with timestamp <= current_timestamp, then validate."""
        symbol = symbol or self.default_symbol
        current = to_timestamp(current_timestamp)
        history = self._frame[
            (self._frame["symbol"] == symbol) & (self._frame["timestamp"] <= current)
        ].copy()
        if lookback is not None:
            history = history.iloc[-lookback:]
        actions = self.get_corporate_actions(current, symbol=symbol)
        validate_context(history, current, corporate_actions=actions)
        if history.empty:
            raise InsufficientHistoryError(f"No history for {symbol} at {current}")
        if timestamps_of(history).max() > current:
            raise LookAheadBiasError("get_history leaked future rows")
        return history.reset_index(drop=True)

    def get_range(
        self,
        start: pd.Timestamp | str,
        end: pd.Timestamp | str,
        *,
        symbol: str | None = None,
        inclusive_end: bool = False,
    ) -> pd.DataFrame:
        symbol = symbol or self.default_symbol
        start_ts = to_timestamp(start)
        end_ts = to_timestamp(end)
        mask = (self._frame["symbol"] == symbol) & (self._frame["timestamp"] >= start_ts)
        mask &= (
            self._frame["timestamp"] <= end_ts if inclusive_end else self._frame["timestamp"] < end_ts
        )
        out = self._frame.loc[mask].copy()
        if not out.empty:
            validate_context(out, timestamps_of(out).max())
        return out.reset_index(drop=True)

    def get_corporate_actions(
        self, current_timestamp: pd.Timestamp | str, *, symbol: str | None = None
    ) -> pd.DataFrame:
        if self._corporate_actions.empty:
            return self._corporate_actions.copy()
        symbol = symbol or self.default_symbol
        current = to_timestamp(current_timestamp)
        actions = self._corporate_actions[
            (self._corporate_actions["symbol"] == symbol)
            & (self._corporate_actions["timestamp"] <= current)
        ].copy()
        validate_context(actions, current)
        return actions.reset_index(drop=True)

    def slice_by_timestamps(
        self, stamps: pd.DatetimeIndex, *, symbol: str | None = None
    ) -> pd.DataFrame:
        symbol = symbol or self.default_symbol
        wanted = pd.DatetimeIndex(stamps)
        data = self._frame[
            (self._frame["symbol"] == symbol) & (self._frame["timestamp"].isin(wanted))
        ].copy()
        return data.reset_index(drop=True)


def _file_fingerprint(path: str | Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def synthetic_ohlcv(
    closes: list[float],
    *,
    start: str = "2020-01-01",
    symbol: str = "TEST",
    freq: str = "D",
    volume: float = 1_000.0,
) -> pd.DataFrame:
    """Build a tiny deterministic OHLCV frame for tests and examples."""
    index = pd.date_range(start=start, periods=len(closes), freq=freq)
    rows: list[dict[str, Any]] = []
    previous = closes[0]
    for stamp, close in zip(index, closes):
        open_px = previous
        high = max(open_px, close) + 1.0
        low = min(open_px, close) - 1.0
        rows.append(
            {
                "timestamp": stamp,
                "symbol": symbol,
                "open": float(open_px),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
            }
        )
        previous = close
    # First bar: open equals close so the series is the advertised close path.
    rows[0]["open"] = float(closes[0])
    rows[0]["high"] = float(closes[0]) + 1.0
    rows[0]["low"] = float(closes[0]) - 1.0
    return pd.DataFrame(rows)
