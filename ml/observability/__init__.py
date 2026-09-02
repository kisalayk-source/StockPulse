"""Prediction observability helpers."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ml.prediction")


def log_prediction(event: dict[str, Any]) -> None:
    logger.info(
        "prediction",
        extra={
            "ticker": event.get("ticker"),
            "timestamp": event.get("timestamp"),
            "feature_version": event.get("feature_version"),
            "horizon": event.get("horizon"),
            "signal": event.get("signal"),
            "probability": event.get("probability"),
            "risk_score": event.get("risk_score"),
            "latency_ms": event.get("latency_ms"),
            "model_versions": event.get("model_versions"),
        },
    )
