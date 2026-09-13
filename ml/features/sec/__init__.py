"""SEC flow features (MVP-3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ml.features.feature_schema import normalize_feature_dict
from ml.features.sec.institutional_flow import institutional_flow_features
from ml.features.sec.insider_flow import insider_flow_features
from ml.features.sec.ownership import ownership_features


def compute_sec_features(
    events: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> dict[str, float]:
    """Merge institutional, insider, and ownership flow features at ``as_of``."""
    values: dict[str, float] = {}
    values.update(institutional_flow_features(events, as_of=as_of))
    values.update(insider_flow_features(events, as_of=as_of))
    values.update(ownership_features(events, as_of=as_of))
    return normalize_feature_dict(values)


__all__ = [
    "compute_sec_features",
    "institutional_flow_features",
    "insider_flow_features",
    "ownership_features",
]
