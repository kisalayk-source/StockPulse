"""Simple filesystem model registry."""

from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ModelRecord:
    model_id: str
    model_type: str
    version: str
    feature_version: str
    prediction_horizon: str
    training_period: str
    training_timestamp: str
    training_cutoff: str
    validation_metrics: dict[str, float] = field(default_factory=dict)
    test_metrics: dict[str, float] = field(default_factory=dict)
    status: str = "active"
    artifact_path: str | None = None


class ModelRegistry:
    def __init__(self, store_dir: Path | str) -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.store_dir / "index.json"
        self._index: dict[str, dict[str, Any]] = {}
        if self.index_path.exists():
            self._index = json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self) -> None:
        self.index_path.write_text(json.dumps(self._index, indent=2), encoding="utf-8")

    def key(self, ticker: str, horizon: str, feature_version: str, model_type: str = "xgboost") -> str:
        return f"{model_type}:{ticker.upper()}:{horizon}:{feature_version}"

    def get(self, key: str) -> ModelRecord | None:
        payload = self._index.get(key)
        if not payload:
            return None
        return ModelRecord(**{k: v for k, v in payload.items() if k in ModelRecord.__dataclass_fields__})

    def load_artifact(self, key: str) -> Any | None:
        record = self.get(key)
        if record is None or not record.artifact_path:
            return None
        path = Path(record.artifact_path)
        if not path.exists():
            return None
        with path.open("rb") as handle:
            return pickle.load(handle)

    def save(
        self,
        key: str,
        *,
        model: Any,
        record: ModelRecord,
    ) -> ModelRecord:
        artifact = self.store_dir / f"{key.replace(':', '_')}.pkl"
        with artifact.open("wb") as handle:
            pickle.dump(model, handle)
        record.artifact_path = str(artifact)
        self._index[key] = asdict(record)
        self._save_index()
        return record

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
