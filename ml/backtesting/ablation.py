"""Feature-group ablation helpers (MVP-6)."""

from __future__ import annotations

from typing import Iterable

from ml.features.feature_schema import (
    FUNDAMENTAL_FEATURE_KEYS,
    SEC_FEATURE_KEYS,
    TECHNICAL_FEATURE_KEYS,
)

# Sub-groups within technical features for finer ablation.
TECHNICAL_GROUPS: dict[str, tuple[str, ...]] = {
    "trend": (
        "sma_10",
        "sma_20",
        "sma_50",
        "sma_100",
        "sma_200",
        "ema_10",
        "ema_20",
        "ema_50",
        "ema_200",
        "distance_from_sma20",
        "distance_from_sma50",
        "distance_from_sma200",
    ),
    "momentum": ("rsi", "macd", "macd_signal", "macd_histogram", "roc", "momentum"),
    "volatility": (
        "atr",
        "bollinger_upper",
        "bollinger_middle",
        "bollinger_lower",
        "bollinger_width",
        "bollinger_percent_b",
        "rolling_volatility",
        "rolling_volatility_annualized",
    ),
    "volume": ("volume_sma", "volume_ratio", "volume_acceleration", "obv", "price_volume_corr"),
    "structure": (
        "high_breakout_20",
        "low_breakout_20",
        "drawdown",
        "return_1d",
        "return_5d",
        "return_20d",
    ),
}

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "technical": TECHNICAL_FEATURE_KEYS,
    "sec": SEC_FEATURE_KEYS,
    "fundamentals": FUNDAMENTAL_FEATURE_KEYS,
    **TECHNICAL_GROUPS,
}


def resolve_feature_mask(
    all_columns: Iterable[str],
    *,
    drop_groups: Iterable[str] | None = None,
    keep_groups: Iterable[str] | None = None,
    drop_columns: Iterable[str] | None = None,
) -> list[str]:
    """Return ordered feature columns after ablation filters.

    ``drop_groups`` removes named groups (e.g. ``momentum``, ``sec``).
    ``keep_groups`` if set, keeps only those groups (intersection with available cols).
    """
    columns = [c for c in all_columns if c not in {"target", "forward_return"}]
    drop_set: set[str] = set(drop_columns or ())
    for group in drop_groups or ():
        keys = FEATURE_GROUPS.get(str(group))
        if keys:
            drop_set.update(keys)
        else:
            drop_set.add(str(group))

    if keep_groups:
        keep_set: set[str] = set()
        for group in keep_groups:
            keys = FEATURE_GROUPS.get(str(group))
            if keys:
                keep_set.update(keys)
            else:
                keep_set.add(str(group))
        columns = [c for c in columns if c in keep_set]

    return [c for c in columns if c not in drop_set]


def apply_feature_mask(dataset_columns: Iterable[str], mask: Iterable[str]) -> list[str]:
    allowed = set(mask)
    return [c for c in dataset_columns if c in allowed or c in {"target", "forward_return"}]
