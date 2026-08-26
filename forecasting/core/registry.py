"""Config-driven model registry."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from forecasting.core.base import ForecastModel

logger = logging.getLogger("forecasting.registry")

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "models.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load models.yaml (PyYAML)."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML is required: pip install pyyaml") from exc

    cfg_path = Path(path) if path else DEFAULT_CONFIG
    with cfg_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"invalid config root in {cfg_path}")
    return data


def _import_adapter(dotted: str) -> type[ForecastModel]:
    module_name, _, class_name = dotted.rpartition(".")
    if not module_name or not class_name:
        raise ValueError(f"invalid adapter path: {dotted}")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    if not isinstance(cls, type):
        raise TypeError(f"{dotted} is not a class")
    return cls  # type: ignore[return-value]


def get_active_models(
    path: str | Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> list[ForecastModel]:
    """Instantiate enabled adapters from config. Does not call load()."""
    cfg = config if config is not None else load_config(path)
    models_cfg = cfg.get("models") or {}
    active: list[ForecastModel] = []
    for name, entry in models_cfg.items():
        if not isinstance(entry, dict):
            continue
        if not entry.get("enabled", False):
            continue
        adapter_path = entry.get("adapter")
        if not adapter_path:
            logger.warning("model %s missing adapter path; skipping", name)
            continue
        params = dict(entry.get("params") or {})
        try:
            cls = _import_adapter(str(adapter_path))
            instance = cls(**params)
            # Allow config key to override instance.name when useful
            if not getattr(instance, "name", None):
                instance.name = str(name)
            active.append(instance)
        except Exception as exc:  # noqa: BLE001 — optional model may be missing
            logger.warning("failed to load adapter %s (%s): %s", name, adapter_path, exc)
    return active


def get_model_weights(
    path: str | Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Return {model_name: weight} for enabled models."""
    cfg = config if config is not None else load_config(path)
    weights: dict[str, float] = {}
    for name, entry in (cfg.get("models") or {}).items():
        if not isinstance(entry, dict) or not entry.get("enabled", False):
            continue
        weights[str(name)] = float(entry.get("weight", 1.0))
    return weights


def get_ensemble_settings(
    path: str | Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config if config is not None else load_config(path)
    return dict(cfg.get("ensemble") or {"strategy": "weighted_average"})
