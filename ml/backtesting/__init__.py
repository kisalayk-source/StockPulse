"""Prediction backtesting (MVP-6): walk-forward, ablation, SHAP, metrics."""

from __future__ import annotations

from typing import Any

from ml.backtesting.ablation import FEATURE_GROUPS, apply_feature_mask, resolve_feature_mask
from ml.backtesting.benchmark import buy_and_hold_return, compare_to_benchmarks
from ml.backtesting.engine import run_ablation, run_backtest
from ml.backtesting.metrics import aggregate_fold_metrics, classification_metrics, summarize_metrics
from ml.backtesting.shap_explain import explain_tree_model, shap_available
from ml.backtesting.walk_forward import WalkForwardFold, walk_forward_splits

__all__ = [
    "FEATURE_GROUPS",
    "WalkForwardFold",
    "aggregate_fold_metrics",
    "apply_feature_mask",
    "buy_and_hold_return",
    "classification_metrics",
    "compare_to_benchmarks",
    "explain_tree_model",
    "resolve_feature_mask",
    "run_ablation",
    "run_backtest",
    "shap_available",
    "summarize_metrics",
    "walk_forward_splits",
]


# Back-compat: previous scaffold exposed run_backtest at package root.
def __getattr__(name: str) -> Any:  # pragma: no cover
    if name == "engine":
        from ml.backtesting import engine as _engine

        return _engine
    raise AttributeError(name)
