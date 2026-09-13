"""MVP-6 walk-forward / ablation / metrics tests."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.backtesting import (
    classification_metrics,
    compare_to_benchmarks,
    resolve_feature_mask,
    run_ablation,
    run_backtest,
    walk_forward_splits,
)
from ml.backtesting.shap_explain import explain_tree_model
from ml.models.xgboost_model import XGBoostModel


def _synthetic_ohlcv(n: int = 260, seed: int = 21) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-03", periods=n, freq="B", tz="UTC")
    returns = rng.normal(0.0004, 0.012, size=n)
    close = 100 * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0.001, 0.012, size=n))
    low = close * (1 - rng.uniform(0.001, 0.012, size=n))
    open_ = close * (1 + rng.normal(0, 0.002, size=n))
    volume = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def test_walk_forward_splits_no_overlap() -> None:
    index = pd.date_range("2024-01-02", periods=200, freq="B", tz="UTC")
    folds = list(
        walk_forward_splits(
            index,
            train_bars=80,
            test_bars=20,
            embargo_bars=5,
            mode="expanding",
            max_folds=4,
        )
    )
    assert len(folds) >= 1
    for fold in folds:
        fold.validate()
        assert fold.train_index.max() < fold.test_index.min()
        # Embargo: at least embargo_bars gap in positional sense on original index
        train_end_pos = index.get_loc(fold.train_index.max())
        test_start_pos = index.get_loc(fold.test_index.min())
        assert int(test_start_pos) - int(train_end_pos) >= 5


def test_classification_metrics_basic() -> None:
    metrics = classification_metrics([1, 0, 1, 1], y_prob=[0.8, 0.2, 0.7, 0.6])
    assert metrics["n"] == 4.0
    assert metrics["accuracy"] == 1.0
    assert 0.0 <= metrics["brier_score"] <= 1.0
    assert metrics["auc"] == metrics["auc"]  # not NaN


def test_resolve_feature_mask_drops_momentum() -> None:
    cols = ["rsi", "macd", "sma_20", "volume_ratio", "drawdown"]
    masked = resolve_feature_mask(cols, drop_groups=["momentum"])
    assert "rsi" not in masked
    assert "macd" not in masked
    assert "sma_20" in masked


def test_run_backtest_walk_forward() -> None:
    pytest.importorskip("xgboost")
    ohlcv = _synthetic_ohlcv(520)
    report = run_backtest(
        ohlcv,
        model_type="xgboost",
        horizon_bars=5,
        train_bars=80,
        test_bars=25,
        max_folds=3,
        model_params={"n_estimators": 20, "max_depth": 3, "n_jobs": 1, "random_state": 0},
        compute_shap=True,
    )
    assert report["n_folds"] >= 1
    assert report["overall"]["n"] > 0
    assert "accuracy" in report["overall"]
    assert "brier_score" in report["metrics"] or "overall_brier_score" in report["metrics"]
    assert report["shap"]["available"] in {True, False}
    assert isinstance(report["shap"]["features"], dict)
    # Leakage: each fold train ends before test starts
    for fold in report["folds"]:
        assert fold["train_end"] < fold["test_start"]


def test_ablation_changes_feature_set() -> None:
    pytest.importorskip("xgboost")
    ohlcv = _synthetic_ohlcv(480)
    kwargs = {
        "model_type": "xgboost",
        "horizon_bars": 5,
        "train_bars": 80,
        "test_bars": 25,
        "max_folds": 2,
        "model_params": {"n_estimators": 15, "max_depth": 3, "n_jobs": 1, "random_state": 1},
        "compute_shap": False,
    }
    full = run_backtest(ohlcv, **kwargs)
    ablated = run_backtest(ohlcv, drop_groups=["momentum"], **kwargs)
    assert set(ablated["feature_columns"]).isdisjoint({"rsi", "macd", "roc", "momentum"})
    assert len(ablated["feature_columns"]) < len(full["feature_columns"])


def test_run_ablation_summary() -> None:
    pytest.importorskip("xgboost")
    ohlcv = _synthetic_ohlcv(480)
    result = run_ablation(
        ohlcv,
        groups=["momentum"],
        baseline_kwargs={
            "model_type": "xgboost",
            "horizon_bars": 5,
            "train_bars": 80,
            "test_bars": 25,
            "max_folds": 2,
            "model_params": {"n_estimators": 15, "max_depth": 3, "n_jobs": 1, "random_state": 2},
        },
    )
    assert "baseline" in result
    assert "momentum" in result["ablations"]
    assert "accuracy_delta_vs_baseline" in result


def test_compare_to_benchmarks() -> None:
    out = compare_to_benchmarks(
        closes=[100.0, 110.0],
        y_true=[1, 0, 1],
        model_metrics={"accuracy": 0.66, "hit_rate": 0.66},
    )
    assert out["buy_and_hold_return"] == pytest.approx(0.1)
    assert "always_long" in out


def test_explain_tree_falls_back_without_crash() -> None:
    pytest.importorskip("xgboost")
    ohlcv = _synthetic_ohlcv(400)
    from ml.features.feature_pipeline import compute_technical_frame
    from ml.models.targets import add_forward_return_target

    frame = compute_technical_frame(ohlcv)
    dataset = add_forward_return_target(ohlcv, frame, horizon_bars=5)
    # Use a wide window so both classes appear after SMA warm-up.
    train = dataset.iloc[:150]
    assert train["target"].nunique() >= 2
    model = XGBoostModel(params={"n_estimators": 10, "max_depth": 2, "n_jobs": 1, "random_state": 0})
    model.train(train)
    explanation = explain_tree_model(model, train.drop(columns=["target", "forward_return"]))
    assert explanation["available"] is True
    assert explanation["method"] in {"shap", "feature_importances"}
    assert explanation["features"]
