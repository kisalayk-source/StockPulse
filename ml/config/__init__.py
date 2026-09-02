"""Load prediction YAML configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "prediction.yaml"


def load_prediction_config(path: Path | str | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("prediction config must be a mapping")
    return data


@lru_cache
def get_prediction_config() -> dict[str, Any]:
    return load_prediction_config()


def horizon_to_bars(horizon: str) -> int:
    mapping = {"1d": 1, "5d": 5, "20d": 20}
    key = horizon.strip().lower()
    if key not in mapping:
        raise ValueError(f"unsupported horizon: {horizon}")
    return mapping[key]
