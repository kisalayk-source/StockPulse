"""Walk-forward backtest engine for hybrid directional models (MVP-6)."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

from ml.backtesting.ablation import resolve_feature_mask
from ml.backtesting.benchmark import compare_to_benchmarks
from ml.backtesting.metrics import (
    aggregate_fold_metrics,
    classification_metrics,
    information_coefficient,
    summarize_metrics,
)
from ml.backtesting.shap_explain import explain_tree_model
from ml.backtesting.walk_forward import WalkForwardFold, walk_forward_splits
from ml.features.feature_pipeline import compute_technical_frame
from ml.models.lightgbm_model import LightGBMModel
from ml.models.targets import add_forward_return_target
from ml.models.xgboost_model import XGBoostModel


_MODEL_TYPES: dict[str, type] = {
    "xgboost": XGBoostModel,
    "lightgbm": LightGBMModel,
}


def run_backtest(
    ohlcv: pd.DataFrame,
    *,
    model_type: str = "xgboost",
    model_cls: type | None = None,
    horizon_bars: int = 5,
    return_threshold: float = 0.0,
    train_bars: int = 120,
    test_bars: int = 40,
    step_bars: int | None = None,
    embargo_bars: int | None = None,
    mode: str = "expanding",
    max_folds: int | None = 8,
    model_params: dict[str, Any] | None = None,
    drop_groups: Iterable[str] | None = None,
    keep_groups: Iterable[str] | None = None,
    compute_shap: bool = True,
    shap_top_k: int = 12,
) -> dict[str, Any]:
    """Run purged walk-forward evaluation for a single tree model type.

    Reuses ``compute_technical_frame`` + ``add_forward_return_target`` and the
    same XGB/LGBM adapters as live prediction — no parallel training stack.
    """
    if ohlcv is None or ohlcv.empty:
        raise ValueError("ohlcv is required")
    if "close" not in ohlcv.columns:
        raise ValueError("ohlcv must include close")

    cls = model_cls or _MODEL_TYPES.get(str(model_type).lower())
    if cls is None:
        raise ValueError(f"unsupported model_type: {model_type}")

    embargo = int(embargo_bars if embargo_bars is not None else horizon_bars)
    feature_frame = compute_technical_frame(ohlcv)
    dataset = add_forward_return_target(
        ohlcv,
        feature_frame,
        horizon_bars=horizon_bars,
        threshold=return_threshold,
    )
    if dataset.empty:
        raise ValueError("no labeled rows after feature/target construction")

    feature_cols = resolve_feature_mask(
        [c for c in dataset.columns if c not in {"target", "forward_return"}],
        drop_groups=drop_groups,
        keep_groups=keep_groups,
    )
    if not feature_cols:
        raise ValueError("ablation removed all feature columns")

    labeled = dataset[feature_cols + ["target", "forward_return"]].dropna()
    folds = list(
        walk_forward_splits(
            labeled.index,
            train_bars=train_bars,
            test_bars=test_bars,
            step_bars=step_bars,
            embargo_bars=embargo,
            mode=mode,  # type: ignore[arg-type]
            max_folds=max_folds,
        )
    )
    if not folds:
        raise ValueError(
            f"need more history for walk-forward "
            f"(rows={len(labeled)}, train_bars={train_bars}, test_bars={test_bars}, embargo={embargo})"
        )

    fold_reports: list[dict[str, Any]] = []
    all_y: list[float] = []
    all_p: list[float] = []
    all_r: list[float] = []
    last_model: Any | None = None
    last_train_frame: pd.DataFrame | None = None

    for fold in folds:
        report, model = _evaluate_fold(
            labeled,
            fold,
            model_cls=cls,
            feature_cols=feature_cols,
            model_params=model_params or {},
        )
        fold_reports.append(report)
        all_y.extend(report["y_true"])
        all_p.extend(report["y_prob"])
        all_r.extend(report["forward_return"])
        last_model = model
        last_train_frame = labeled.loc[fold.train_index, feature_cols]

    aggregated = aggregate_fold_metrics(
        [{k: v for k, v in row["metrics"].items()} for row in fold_reports]
    )
    if all_r and all_p:
        aggregated["information_coefficient"] = information_coefficient(all_r, all_p)
    overall = classification_metrics(all_y, y_prob=all_p)
    for key, value in overall.items():
        aggregated.setdefault(f"overall_{key}", value)

    shap_summary: dict[str, Any] = {"method": "none", "features": {}, "available": False}
    if compute_shap and last_model is not None and last_train_frame is not None:
        shap_summary = explain_tree_model(last_model, last_train_frame, top_k=shap_top_k)

    closes = [float(x) for x in ohlcv.loc[labeled.index, "close"].tolist()]
    benchmarks = compare_to_benchmarks(closes=closes, y_true=all_y, model_metrics=overall)

    compact_folds = [
        {
            "fold_id": row["fold_id"],
            "train_start": row["train_start"],
            "train_end": row["train_end"],
            "test_start": row["test_start"],
            "test_end": row["test_end"],
            "metrics": row["metrics"],
            "train_rows": row["train_rows"],
            "test_rows": row["test_rows"],
        }
        for row in fold_reports
    ]

    return {
        "model_type": getattr(cls, "name", str(model_type)),
        "horizon_bars": int(horizon_bars),
        "mode": mode,
        "embargo_bars": embargo,
        "feature_columns": feature_cols,
        "drop_groups": list(drop_groups or []),
        "keep_groups": list(keep_groups or []),
        "n_folds": len(compact_folds),
        "folds": compact_folds,
        "metrics": summarize_metrics(aggregated),
        "overall": summarize_metrics(overall),
        "benchmarks": benchmarks,
        "shap": shap_summary,
    }


def run_ablation(
    ohlcv: pd.DataFrame,
    *,
    groups: Iterable[str] | None = None,
    baseline_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare full-feature backtest vs dropping each feature group."""
    base_kwargs = dict(baseline_kwargs or {})
    base_kwargs.setdefault("compute_shap", False)
    baseline = run_backtest(ohlcv, **base_kwargs)
    results: dict[str, Any] = {"baseline": baseline}
    dropped: dict[str, Any] = {}
    for group in groups or ("momentum", "volatility", "volume", "structure", "trend"):
        try:
            dropped[group] = run_backtest(ohlcv, drop_groups=[group], **base_kwargs)
        except Exception as exc:
            dropped[group] = {"error": f"{type(exc).__name__}: {exc}"}
    results["ablations"] = dropped

    baseline_acc = float((baseline.get("overall") or {}).get("accuracy") or np.nan)
    deltas: dict[str, float] = {}
    for group, payload in dropped.items():
        if "error" in payload:
            continue
        acc = float((payload.get("overall") or {}).get("accuracy") or np.nan)
        if baseline_acc == baseline_acc and acc == acc:
            deltas[group] = acc - baseline_acc
    results["accuracy_delta_vs_baseline"] = deltas
    return results


def _evaluate_fold(
    labeled: pd.DataFrame,
    fold: WalkForwardFold,
    *,
    model_cls: type,
    feature_cols: list[str],
    model_params: dict[str, Any],
) -> tuple[dict[str, Any], Any]:
    train = labeled.loc[fold.train_index]
    test = labeled.loc[fold.test_index]
    train_ds = train[feature_cols + ["target", "forward_return"]]
    model = model_cls(params=model_params)
    model.train(train_ds)

    y_true: list[float] = []
    y_prob: list[float] = []
    forwards: list[float] = []
    for ts, row in test.iterrows():
        feats = {c: float(row[c]) for c in feature_cols if pd.notna(row[c])}
        try:
            prob = float(model.predict_probability(feats))
        except Exception:
            continue
        y_true.append(float(row["target"]))
        y_prob.append(prob)
        forwards.append(float(row["forward_return"]))

    metrics = classification_metrics(y_true, y_prob=y_prob)
    if forwards and y_prob:
        metrics["information_coefficient"] = information_coefficient(forwards, y_prob)

    report = {
        "fold_id": fold.fold_id,
        "train_start": fold.train_start.isoformat(),
        "train_end": fold.train_end.isoformat(),
        "test_start": fold.test_start.isoformat(),
        "test_end": fold.test_end.isoformat(),
        "train_rows": int(len(train_ds)),
        "test_rows": int(len(y_true)),
        "metrics": summarize_metrics(metrics),
        "y_true": y_true,
        "y_prob": y_prob,
        "forward_return": forwards,
    }
    return report, model
