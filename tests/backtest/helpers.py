from __future__ import annotations

import pandas as pd


def ohlcv_frame(
    rows: list[tuple[str, float, float]],
    *,
    symbol: str = "TEST",
    extra: dict | None = None,
) -> pd.DataFrame:
    """rows: (timestamp, open, close)."""
    records = []
    for stamp, open_px, close_px in rows:
        record = {
            "timestamp": pd.Timestamp(stamp),
            "symbol": symbol,
            "open": open_px,
            "high": max(open_px, close_px) + 1,
            "low": min(open_px, close_px) - 1,
            "close": close_px,
            "volume": 1_000.0,
        }
        if extra and stamp in extra:
            record.update(extra[stamp])
        records.append(record)
    return pd.DataFrame(records)


def daily_closes(closes: list[float], start: str = "2020-01-01", symbol: str = "TEST") -> pd.DataFrame:
    index = pd.bdate_range(start, periods=len(closes))
    rows = []
    prev = closes[0]
    for stamp, close in zip(index, closes):
        rows.append((str(stamp.date()), float(prev), float(close)))
        prev = close
    rows[0] = (rows[0][0], closes[0], closes[0])
    return ohlcv_frame(rows, symbol=symbol)
