"""Directional ensemble strategies (MVP-2)."""

from __future__ import annotations

from typing import Any


def _finite_score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number < 0:
        return None
    return number


def combine_probabilities(
    members: dict[str, float],
    *,
    weights: dict[str, float] | None = None,
    scores: dict[str, float] | None = None,
    strategy: str = "equal_weight",
) -> float:
    if not members:
        raise ValueError("no model probabilities to combine")
    if strategy == "equal_weight":
        return sum(members.values()) / len(members)
    if strategy == "performance_weighted":
        effective: dict[str, float] = {}
        for name in members:
            yaml_weight = float((weights or {}).get(name, 1.0))
            score = _finite_score(None if scores is None else scores.get(name))
            if score is None:
                effective[name] = yaml_weight
            else:
                effective[name] = 1.0 / max(score, 1e-4)
        return _weighted_mean(members, effective)
    raise ValueError(f"unsupported ensemble strategy: {strategy}")


def _weighted_mean(members: dict[str, float], weights: dict[str, float]) -> float:
    total = 0.0
    weight_sum = 0.0
    for name, probability in members.items():
        weight = float(weights.get(name, 0.0))
        total += probability * weight
        weight_sum += weight
    if weight_sum <= 0:
        return sum(members.values()) / len(members)
    return total / weight_sum


def model_agreement(members: dict[str, float], *, threshold: float = 0.5) -> float:
    """1 when member probabilities cluster, 0 when they spread by 0.25 or more.

    ``threshold`` is unused. Agreement is the spread of probabilities, not a
    vote at 0.5, so 0.51 and 0.99 do not count as the same view.
    """
    _ = threshold
    if not members:
        return 0.0
    values = [float(probability) for probability in members.values()]
    if len(values) == 1:
        return 1.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    spread = variance ** 0.5
    return float(max(0.0, min(1.0, 1.0 - min(1.0, spread / 0.25))))
