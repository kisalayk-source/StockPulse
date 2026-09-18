"""Load government YAML configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import ROOT_DIR, Settings


def _default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "mapping": {
            "min_confidence": 0.75,
            "fuzzy_min_confidence": 0.55,
            "fuzzy_accept_confidence": 0.85,
        },
        "scoring": {
            "award": 30,
            "sole_source": 20,
            "large_opportunity": 15,
            "new_customer": 10,
            "multi_year": 10,
            "material_revenue": 10,
            "backlog_impact": 10,
            "incumbent": 5,
            "idiq_ceiling_only": -20,
            "option_only": -15,
            "immaterial_contract": -10,
        },
        "early_signal": {
            "PROCUREMENT_FORECAST": 100,
            "SOURCES_SOUGHT": 90,
            "PRESOLICITATION": 80,
            "SOLICITATION": 70,
            "AWARD": 50,
            "AWARD_MODIFICATION": 45,
            "OBLIGATION": 30,
            "OPTION_EXERCISED": 35,
        },
        "thresholds": {
            "large_opportunity_amount": 50_000_000,
            "large_award_amount": 25_000_000,
            "large_obligation_amount": 10_000_000,
            "material_revenue_ratio": 0.05,
            "immaterial_revenue_ratio": 0.005,
            "multi_year_days": 365,
        },
        "alerts": {
            "government_score_min": 80,
            "large_award_amount": 25_000_000,
            "large_obligation_amount": 10_000_000,
            "large_opportunity_amount": 50_000_000,
            "new_customer": True,
            "sole_source": True,
        },
        "ingest": {
            "lookback_days": 90,
            "page_limit": 100,
            "max_pages": 5,
        },
    }


def load_government_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg = _default_config()
    if path is None:
        return cfg
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = ROOT_DIR / file_path
    if not file_path.exists():
        return cfg
    with file_path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        return cfg
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            merged = dict(cfg[key])
            merged.update(value)
            cfg[key] = merged
        else:
            cfg[key] = value
    return cfg


@lru_cache
def get_government_config(path: str = "backend/configs/government.yaml") -> dict[str, Any]:
    return load_government_config(path)


def government_config_for_settings(settings: Settings) -> dict[str, Any]:
    return load_government_config(settings.government_config_path)
