"""Directional ensemble strategies (MVP-2)."""

from __future__ import annotations

from typing import Any


def combine_probabilities(
    members: dict[str, float],
    *,
    weights: dict[str, float] | None = None,
    strategy: str = "equal_weight",
) -> float:
    if not members:
        raise ValueError("no model probabilities to combine")
    if strategy == "equal_weight":
        return sum(members.values()) / len(members)
    if strategy in {"performance_weighted", "regime_weighted", "meta_model"}:
        if not weights:
            return sum(members.values()) / len(members)
        total = 0.0
        weight_sum = 0.0
        for name, probability in members.items():
            weight = float(weights.get(name, 0.0))
            total += probability * weight
            weight_sum += weight
        if weight_sum <= 0:
            return sum(members.values()) / len(members)
        return total / weight_sum
    raise ValueError(f"unsupported ensemble strategy: {strategy}")


def model_agreement(members: dict[str, float], *, threshold: float = 0.5) -> float:
    if not members:
        return 0.0
    directions = [1 if p >= threshold else 0 for p in members.values()]
    majority = 1 if sum(directions) >= len(directions) / 2 else 0
    return sum(1 for d in directions if d == majority) / len(directions)
