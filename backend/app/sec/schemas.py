from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ComponentScores(BaseModel):
    institutional: float | None = None
    insider: float | None = None
    major_holder: float | None = None
    price_volume: float | None = None
    fundamentals: float | None = None


class EvidenceItem(BaseModel):
    source: str
    accession_number: str | None = None
    filing_date: str | None = None
    reporting_period: str | None = None
    event_type: str
    component: str | None = None
    signal_label: str | None = None
    data_timestamp: str | None = None
    polarity: float | None = None
    detail: str | None = None


class AccumulationResponse(BaseModel):
    ticker: str
    score: float
    signal: str
    classification: str
    components: ComponentScores
    events: list[EvidenceItem] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    as_of: datetime
    provider_errors: list[dict[str, str]] = Field(default_factory=list)


class SecIntelligenceResponse(BaseModel):
    ticker: str
    accumulation: AccumulationResponse
    institutional_changes: list[dict[str, Any]] = Field(default_factory=list)
    insider_transactions: list[dict[str, Any]] = Field(default_factory=list)
    major_holder_changes: list[dict[str, Any]] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class ResearchQueryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)


class ResearchQueryResponse(BaseModel):
    query: str
    filters: dict[str, Any]
    candidates: list[dict[str, Any]]
    narrative: str
    disclaimer: str


class SecFilingsResponse(BaseModel):
    ticker: str
    months: int
    cutoff_date: str
    summary: dict[str, int]
    filings: list[dict[str, Any]]
    insider_transactions: list[dict[str, Any]] = Field(default_factory=list)
    beneficial_ownership: list[dict[str, Any]] = Field(default_factory=list)
    provider_errors: list[dict[str, str]] = Field(default_factory=list)
