"""Canonical prediction data entities and loaders."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Security:
    ticker: str
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None


@dataclass(frozen=True)
class MarketBar:
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class FeatureSnapshot:
    ticker: str
    timestamp: datetime
    feature_version: str
    data_cutoff: datetime
    technical: dict[str, float] = field(default_factory=dict)
    sec: dict[str, float] = field(default_factory=dict)
    fundamentals: dict[str, float] = field(default_factory=dict)
    market_regime: dict[str, Any] = field(default_factory=dict)
    snapshot_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        payload["data_cutoff"] = self.data_cutoff.isoformat()
        return payload


@dataclass
class ModelPrediction:
    ticker: str
    timestamp: datetime
    horizon: str
    model_id: str
    model_type: str
    model_version: str
    feature_version: str
    training_cutoff: datetime
    probability: float
    raw_probability: float
    expected_return: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        payload["training_cutoff"] = self.training_cutoff.isoformat()
        return payload


@dataclass
class RiskAssessment:
    ticker: str
    timestamp: datetime
    risk_score: float
    confidence_score: float
    expected_return: float | None = None
    max_loss_estimate: float | None = None
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass
class TradingSignal:
    ticker: str
    timestamp: datetime
    horizon: str
    signal: str
    probability: float
    risk_score: float
    confidence: float
    model_agreement: float | None = None
    feature_snapshot_id: str | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass
class PredictionExplanation:
    ticker: str
    timestamp: datetime
    signal: str
    text: str
    structured: dict[str, Any] = field(default_factory=dict)
    provider: str = "template"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload
