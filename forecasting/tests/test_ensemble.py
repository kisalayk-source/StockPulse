"""Ensemble strategy tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from forecasting.core.schema import ForecastResult
from forecasting.ensemble.strategies import (
    fit_stacking_ridge,
    inverse_error_weights,
    stacking_combine,
    weighted_average,
)


def _result(name: str, closes: list[float]) -> ForecastResult:
    return ForecastResult(
        model_name=name,
        ticker="T",
        predicted=pd.DataFrame({"close": closes}),
        latency_ms=1.0,
    )


def test_weighted_average_and_disagreement():
    a = _result("a", [100.0, 110.0, 120.0])
    b = _result("b", [100.0, 100.0, 100.0])
    out = weighted_average([a, b], {"a": 1.0, "b": 1.0})
    assert out.model_name == "ensemble"
    assert list(out.predicted["close"]) == [100.0, 105.0, 110.0]
    assert "disagreement" in out.meta
    assert out.meta["disagreement"]["final_close_std"] > 0


def test_inverse_error_weights():
    weights = inverse_error_weights({"a": 2.0, "b": 1.0})
    assert weights["b"] > weights["a"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_stacking_ridge_and_combine():
    members = np.array([[1.0, 2.0], [2.0, 3.0], [3.0, 4.0]])
    actuals = np.array([1.5, 2.5, 3.5])
    coefs, intercept = fit_stacking_ridge(members, actuals, member_names=["a", "b"], alpha=0.1)
    assert set(coefs) == {"a", "b"}
    a = _result("a", [1.0, 2.0, 3.0])
    b = _result("b", [2.0, 3.0, 4.0])
    out = stacking_combine([a, b], coefficients=coefs, intercept=intercept)
    assert out.model_name == "ensemble"
    assert out.meta["strategy"] == "stacking"
    assert len(out.predicted) == 3
