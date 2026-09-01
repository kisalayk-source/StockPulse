from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import ROOT_DIR, Settings


def _resolve_config_path(settings: Settings) -> Path:
    raw = Path(settings.sec_score_config_path)
    if raw.is_absolute():
        return raw
    return ROOT_DIR / raw


@lru_cache
def load_sec_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.exists():
        raise FileNotFoundError(f"SEC score config not found: {path}")
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError("SEC score config must be a mapping")
    return payload


def get_sec_config(settings: Settings) -> dict[str, Any]:
    return load_sec_config(str(_resolve_config_path(settings)))
