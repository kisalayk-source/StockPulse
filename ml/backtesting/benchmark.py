"""Benchmark helpers scaffold (MVP-6)."""

from __future__ import annotations

from typing import Any


def buy_and_hold_return(closes: list[float]) -> float:
    if len(closes) < 2 or closes[0] == 0:
        return 0.0
    return closes[-1] / closes[0] - 1.0


def compare_to_benchmarks(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError("benchmark comparison lands in MVP-6")
