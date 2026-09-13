"""SHAP explanations for tree models (MVP-6).

Uses ``shap.TreeExplainer`` when the optional ``shap`` package is installed;
otherwise falls back to native tree ``feature_importances_``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def shap_available() -> bool:
    try:
        import shap  # noqa: F401

        return True
    except ImportError:
        return False


def explain_tree_model(
    model: Any,
    feature_frame: pd.DataFrame,
    *,
    top_k: int = 15,
    max_rows: int = 200,
) -> dict[str, Any]:
    """Return top-k mean |SHAP| (or importance) values for a fitted tree model.

    ``model`` may be an ``XGBoostModel`` / ``LightGBMModel`` adapter or a raw
    sklearn/xgboost/lightgbm estimator exposing ``predict_proba`` /
    ``feature_importances_``.
    """
    estimator, feature_names = _unwrap(model)
    if feature_frame.empty or not feature_names:
        return {"method": "none", "features": {}, "available": False}

    cols = [c for c in feature_names if c in feature_frame.columns]
    if not cols:
        return {"method": "none", "features": {}, "available": False}

    sample = feature_frame[cols].replace([np.inf, -np.inf], np.nan).dropna()
    if sample.empty:
        return {"method": "none", "features": {}, "available": False}
    if len(sample) > max_rows:
        sample = sample.iloc[-max_rows:]

    if shap_available():
        try:
            import shap

            explainer = shap.TreeExplainer(estimator)
            values = explainer.shap_values(sample)
            if isinstance(values, list):
                # binary classifiers often return [class0, class1]
                matrix = np.asarray(values[1] if len(values) > 1 else values[0], dtype=float)
            else:
                matrix = np.asarray(values, dtype=float)
            if matrix.ndim == 3:
                matrix = matrix[:, :, -1]
            mean_abs = np.mean(np.abs(matrix), axis=0)
            ranking = _topk_dict(cols, mean_abs, top_k)
            return {
                "method": "shap",
                "features": ranking,
                "available": True,
                "n_rows": int(len(sample)),
            }
        except Exception as exc:
            fallback = _importance_fallback(estimator, cols, top_k)
            fallback["error"] = f"{type(exc).__name__}: {exc}"
            return fallback

    return _importance_fallback(estimator, cols, top_k)


def _unwrap(model: Any) -> tuple[Any, list[str]]:
    if hasattr(model, "_model") and getattr(model, "_model") is not None:
        names = list(getattr(model, "feature_names", []) or [])
        return model._model, names
    names = list(getattr(model, "feature_names_in_", []) or getattr(model, "feature_name_", []) or [])
    if hasattr(names, "tolist"):
        names = list(names.tolist())
    return model, [str(n) for n in names]


def _importance_fallback(estimator: Any, cols: list[str], top_k: int) -> dict[str, Any]:
    importances = getattr(estimator, "feature_importances_", None)
    if importances is None:
        return {"method": "none", "features": {}, "available": False}
    values = np.asarray(importances, dtype=float)
    n = min(len(cols), len(values))
    ranking = _topk_dict(cols[:n], values[:n], top_k)
    return {"method": "feature_importances", "features": ranking, "available": True}


def _topk_dict(names: list[str], values: np.ndarray, top_k: int) -> dict[str, float]:
    order = np.argsort(values)[::-1][: max(1, top_k)]
    return {str(names[i]): float(values[i]) for i in order if i < len(names)}
