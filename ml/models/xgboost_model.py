"""XGBoost directional classifier adapter."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml.models.base import ForecastModel


def _as_frame(features: pd.DataFrame | dict[str, float]) -> pd.DataFrame:
    if isinstance(features, dict):
        return pd.DataFrame([features])
    return features


class XGBoostModel(ForecastModel):
    name = "xgboost"
    version = "1.0"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = {
            "n_estimators": 80,
            "max_depth": 4,
            "learning_rate": 0.08,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "reg_lambda": 1.0,
            "min_child_weight": 2,
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "n_jobs": 1,
            "random_state": 42,
        }
        if params:
            self.params.update(params)
        self._model: Any | None = None
        self.feature_names: list[str] = []
        self.training_rows: int = 0

    def train(self, dataset: pd.DataFrame) -> None:
        if "target" not in dataset.columns:
            raise ValueError("dataset must include target column")
        feature_frame = dataset.drop(columns=["target", "forward_return"], errors="ignore")
        feature_frame = feature_frame.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan)
        feature_frame = feature_frame.dropna(axis=1, how="all")
        aligned = feature_frame.dropna()
        labels = dataset.loc[aligned.index, "target"].astype(int)
        if aligned.empty or labels.nunique() < 2:
            raise ValueError("insufficient training diversity for xgboost")

        from xgboost import XGBClassifier

        self.feature_names = list(aligned.columns)
        self.training_rows = len(aligned)
        model = XGBClassifier(**self.params)
        model.fit(aligned[self.feature_names], labels)
        self._model = model

    def predict(self, features: pd.DataFrame | dict[str, float]) -> Any:
        probabilities = self._predict_proba_matrix(features)
        return (probabilities[:, 1] >= 0.5).astype(int)

    def predict_probability(self, features: pd.DataFrame | dict[str, float]) -> float:
        matrix = self._predict_proba_matrix(features)
        return float(matrix[-1, 1])

    def _predict_proba_matrix(self, features: pd.DataFrame | dict[str, float]) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("model is not trained")
        frame = _as_frame(features)
        row = pd.DataFrame([{name: float(frame.iloc[-1].get(name, np.nan)) for name in self.feature_names}])
        row = row.fillna(0.0)
        return self._model.predict_proba(row[self.feature_names])
