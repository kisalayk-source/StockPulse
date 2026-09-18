"""Event-study style market reaction using existing OHLCV bars."""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

import pandas as pd

from app.config import ROOT_DIR

_root = str(ROOT_DIR)
if _root not in sys.path:
    sys.path.insert(0, _root)

from ml.data.loaders import bars_to_ohlcv


def compute_market_reaction(
    bars: list[dict[str, Any]],
    event_at: datetime | str | pd.Timestamp,
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 20),
) -> dict[str, float | None]:
    """Forward close-to-close returns after the first bar on/after event_at."""
    if not bars:
        return {f"return_{h}d": None for h in horizons}

    ohlcv = bars_to_ohlcv(bars)
    if ohlcv.empty or "close" not in ohlcv.columns:
        return {f"return_{h}d": None for h in horizons}

    cutoff = pd.Timestamp(event_at)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")

    idx = ohlcv.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
        ohlcv = ohlcv.copy()
        ohlcv.index = idx

    on_or_after = ohlcv.index[ohlcv.index >= cutoff]
    if len(on_or_after) == 0:
        return {f"return_{h}d": None for h in horizons}

    start_pos = int(ohlcv.index.get_loc(on_or_after[0]))
    if isinstance(start_pos, slice):
        start_pos = start_pos.start or 0
    base = float(ohlcv["close"].iloc[start_pos])
    if base <= 0:
        return {f"return_{h}d": None for h in horizons}

    out: dict[str, float | None] = {}
    for horizon in horizons:
        target = start_pos + int(horizon)
        if target >= len(ohlcv):
            out[f"return_{horizon}d"] = None
            continue
        end = float(ohlcv["close"].iloc[target])
        out[f"return_{horizon}d"] = round((end / base) - 1.0, 6)
    return out
