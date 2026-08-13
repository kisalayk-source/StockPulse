from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _floats(bars: list[dict[str, Any]], field: str) -> list[float]:
    values: list[float] = []
    for bar in bars:
        try:
            value = float(bar.get(field))
        except (TypeError, ValueError):
            continue
        if value == value:  # NaN check
            values.append(value)
    return values


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((item - mean) ** 2 for item in values) / (len(values) - 1)
    return variance ** 0.5


def _returns(closes: list[float]) -> list[float]:
    return [
        closes[index] / closes[index - 1] - 1.0
        for index in range(1, len(closes))
        if closes[index - 1]
    ]


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3 or len(left) != len(right):
        return None

    def ranks(values: list[float]) -> list[float]:
        ordered = sorted(range(len(values)), key=lambda index: values[index])
        result = [0.0] * len(values)
        for rank, index in enumerate(ordered, start=1):
            result[index] = float(rank)
        return result

    rx, ry = ranks(left), ranks(right)
    mean_x = sum(rx) / len(rx)
    mean_y = sum(ry) / len(ry)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(rx, ry, strict=True))
    den_x = sum((x - mean_x) ** 2 for x in rx) ** 0.5
    den_y = sum((y - mean_y) ** 2 for y in ry) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round_trip_cost(
    bars: list[dict[str, Any]],
    notional: float = 10_000.0,
    *,
    spread_floor_bps: float = 2.0,
    fee_bps: float = 0.5,
) -> dict[str, float]:
    """Estimate round-trip cost from bar range, volatility, and participation."""
    closes = _floats(bars, "close")
    highs = _floats(bars, "high")
    lows = _floats(bars, "low")
    volumes = _floats(bars, "volume")
    if len(closes) < 5 or len(highs) != len(closes) or len(lows) != len(closes):
        round_trip = 2 * spread_floor_bps + 2.0 + fee_bps
        return {
            "spread_bps": spread_floor_bps,
            "slip_bps": 2.0,
            "fee_bps": fee_bps,
            "round_trip_bps": round_trip,
        }

    ranges = [
        (high - low) / close
        for high, low, close in zip(highs, lows, closes, strict=True)
        if close
    ]
    range_mean = _mean(ranges) or 0.0
    # Range is a decimal return; basis points are decimal * 10,000.
    spread_bps = _clamp(range_mean * 10_000.0, spread_floor_bps, 80.0)
    realized = _std(_returns(closes[-21:])) or 0.01
    adv = 0.0
    if volumes and len(volumes) == len(closes):
        adv = _mean([volume * close for volume, close in zip(volumes, closes, strict=True)]) or 0.0
    participation = min(1.0, notional / adv) if adv > 0 else 0.05
    slip_bps = _clamp(10_000.0 * realized * (participation ** 0.5) * 0.5, 0.5, 40.0)
    round_trip = 2 * (spread_bps + slip_bps) + fee_bps
    return {
        "spread_bps": round(spread_bps, 4),
        "slip_bps": round(slip_bps, 4),
        "fee_bps": fee_bps,
        "round_trip_bps": round(round_trip, 4),
    }


def net_expected_change(gross: float, round_trip_bps: float) -> float:
    haircut = round_trip_bps / 10_000.0
    if gross == 0:
        return -haircut
    sign = 1.0 if gross > 0 else -1.0
    return sign * (abs(gross) - haircut)


def classify_regime(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = _floats(bars, "close")
    if len(closes) < 21:
        return {"label": "unknown", "vol": "unknown", "trend": "unknown", "realized_vol": None}
    returns = _returns(closes)
    short_vol = _std(returns[-20:]) or 0.0
    long_vol = _std(returns[-60:] if len(returns) >= 60 else returns) or short_vol or 1e-9
    ratio = short_vol / long_vol if long_vol else 1.0
    if short_vol >= 0.02 or ratio >= 1.25:
        vol = "high"
    elif short_vol <= 0.007 and ratio <= 0.85:
        vol = "low"
    else:
        vol = "normal"
    fast = _mean(closes[-20:]) or closes[-1]
    slow = _mean(closes[-60:] if len(closes) >= 60 else closes) or fast
    if fast > slow * 1.005:
        trend = "up"
    elif fast < slow * 0.995:
        trend = "down"
    else:
        trend = "sideways"
    return {
        "label": f"{vol}_vol_{trend}",
        "vol": vol,
        "trend": trend,
        "realized_vol": round(short_vol, 6),
    }


def edge_is_reliable(evaluation: dict[str, Any] | None, regime: dict[str, Any] | None = None) -> bool:
    if not evaluation:
        return False
    folds = int(evaluation.get("folds") or 0)
    net = evaluation.get("mean_net_return")
    hit = evaluation.get("hit_rate")
    if folds < 2 or net is None or net <= 0 or (hit or 0) < 0.5:
        return False
    by_regime = evaluation.get("by_regime") or {}
    label = (regime or {}).get("label")
    if label and label in by_regime:
        bucket = by_regime[label]
        bucket_net = bucket.get("mean_net_return")
        if bucket.get("folds", 0) >= 2 and (bucket_net is None or bucket_net <= 0):
            return False
    return True


def walk_forward_evaluate(
    bars: list[dict[str, Any]],
    predict_change: Callable[[list[dict[str, Any]]], float],
    *,
    horizon: int,
    context: int = 32,
    max_folds: int = 3,
    stride: int | None = None,
) -> dict[str, Any]:
    """Purged walk-forward: signal at bar t, fill next open, exit after `horizon` bars."""
    horizon = max(1, int(horizon))
    context = max(8, int(context))
    stride = max(1, stride or max(1, horizon // 2))
    empty = {
        "folds": 0,
        "hit_rate": None,
        "mean_gross_return": None,
        "mean_net_return": None,
        "ic": None,
        "by_regime": {},
        "fill": "next_open",
    }
    if len(bars) < context + horizon + 1 or max_folds <= 0:
        return empty

    folds: list[dict[str, Any]] = []
    end = context
    while end + horizon <= len(bars) and len(folds) < max_folds:
        window = bars[end - context : end]
        fill = bars[end]
        exit_bar = bars[end + horizon - 1]
        try:
            entry = float(fill.get("open") or fill.get("close"))
            exit_price = float(exit_bar.get("close"))
            gross = float(predict_change(window))
        except (TypeError, ValueError):
            end += stride
            continue
        if not entry:
            end += stride
            continue
        realized = exit_price / entry - 1.0
        costs = round_trip_cost(window)
        haircut = costs["round_trip_bps"] / 10_000.0
        predicted_dir = 0 if abs(gross) < 0.002 else (1 if gross > 0 else -1)
        realized_dir = 0 if abs(realized) < 0.002 else (1 if realized > 0 else -1)
        traded_return = predicted_dir * realized if predicted_dir else 0.0
        net = traded_return - haircut if predicted_dir else 0.0
        regime = classify_regime(window)
        folds.append(
            {
                "gross": gross,
                "realized": realized,
                "net": net,
                "hit": predicted_dir != 0 and predicted_dir == realized_dir,
                "regime": regime.get("label"),
            }
        )
        end += stride

    if not folds:
        return empty

    nets = [item["net"] for item in folds]
    gross_realized = [item["realized"] for item in folds]
    forecasts = [item["gross"] for item in folds]
    traded = [item for item in folds if abs(item["gross"]) >= 0.002]
    hit_rate = (sum(1 for item in traded if item["hit"]) / len(traded)) if traded else None
    by_regime: dict[str, dict[str, Any]] = {}
    for item in folds:
        label = item["regime"] or "unknown"
        bucket = by_regime.setdefault(label, {"folds": 0, "nets": []})
        bucket["folds"] += 1
        bucket["nets"].append(item["net"])
    regime_summary = {
        label: {
            "folds": bucket["folds"],
            "mean_net_return": _mean(bucket["nets"]),
        }
        for label, bucket in by_regime.items()
    }
    return {
        "folds": len(folds),
        "hit_rate": hit_rate,
        "mean_gross_return": _mean(gross_realized),
        "mean_net_return": _mean(nets),
        "ic": _spearman(forecasts, gross_realized),
        "by_regime": regime_summary,
        "fill": "next_open",
    }


def score_journal(
    journal: list[dict[str, Any]],
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    timeframe: str,
    horizon: int,
) -> dict[str, Any]:
    """Score completed journal forecasts against later bars (true live OOS)."""
    timestamps = [str(bar.get("timestamp") or "") for bar in bars]
    index = {stamp: position for position, stamp in enumerate(timestamps) if stamp}
    scored: list[dict[str, Any]] = []
    ticker = symbol.upper()
    for item in journal:
        if str(item.get("symbol") or "").upper() != ticker:
            continue
        if item.get("timeframe") != timeframe or int(item.get("horizon") or 0) != horizon:
            continue
        start = index.get(str(item.get("as_of") or ""))
        if start is None:
            continue
        fill_at = start + 1
        exit_at = start + horizon
        if exit_at >= len(bars) or fill_at >= len(bars):
            continue
        try:
            entry = float(bars[fill_at].get("open") or bars[fill_at].get("close"))
            exit_price = float(bars[exit_at].get("close"))
            gross = float(item.get("forecast_change") or 0)
        except (TypeError, ValueError):
            continue
        if not entry:
            continue
        realized = exit_price / entry - 1.0
        haircut = float(item.get("round_trip_bps") or 0) / 10_000.0
        direction = 0 if abs(gross) < 0.002 else (1 if gross > 0 else -1)
        net = direction * realized - haircut if direction else 0.0
        scored.append({"net": net, "hit": direction != 0 and (realized > 0) == (gross > 0), "gross": gross, "realized": realized})
    if not scored:
        return {"samples": 0, "hit_rate": None, "mean_net_return": None}
    traded = [item for item in scored if abs(item["gross"]) >= 0.002]
    return {
        "samples": len(scored),
        "hit_rate": (sum(1 for item in traded if item["hit"]) / len(traded)) if traded else None,
        "mean_net_return": _mean([item["net"] for item in scored]),
    }
