"""Normalized government event types and dataclasses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


EVENT_TYPES = (
    "PROCUREMENT_FORECAST",
    "SOURCES_SOUGHT",
    "PRESOLICITATION",
    "SOLICITATION",
    "AWARD",
    "AWARD_MODIFICATION",
    "OBLIGATION",
    "OPTION_EXERCISED",
)

OPPORTUNITY_TYPES = frozenset(
    {
        "PROCUREMENT_FORECAST",
        "SOURCES_SOUGHT",
        "PRESOLICITATION",
        "SOLICITATION",
    }
)

AWARD_TYPES = frozenset({"AWARD", "AWARD_MODIFICATION", "OPTION_EXERCISED"})
OBLIGATION_TYPES = frozenset({"OBLIGATION"})

# SAM.gov notice type codes → normalized event type
SAM_PTYPE_MAP = {
    "r": "SOURCES_SOUGHT",
    "p": "PRESOLICITATION",
    "o": "SOLICITATION",
    "k": "SOLICITATION",  # combined synopsis/solicitation
    "a": "AWARD",
    "g": "PROCUREMENT_FORECAST",  # sale / special / forecast-ish notices
    "s": "PROCUREMENT_FORECAST",
}


@dataclass
class NormalizedGovernmentEvent:
    event_type: str
    event_id: str
    source: str
    contract_number: str | None = None
    solicitation_number: str | None = None
    company_name: str | None = None
    parent_company: str | None = None
    uei: str | None = None
    cage: str | None = None
    ticker: str | None = None
    cik: str | None = None
    agency: str | None = None
    sub_agency: str | None = None
    title: str | None = None
    description: str | None = None
    naics: str | None = None
    psc: str | None = None
    contract_type: str | None = None
    estimated_value: float | None = None
    ceiling_amount: float | None = None
    awarded_amount: float | None = None
    obligated_amount: float | None = None
    transaction_amount: float | None = None
    posted_date: datetime | None = None
    award_date: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    published_at: datetime | None = None
    event_at: datetime | None = None
    source_url: str | None = None
    sole_source: bool = False
    idiq: bool = False
    option_only: bool = False
    mapping_confidence: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "posted_date",
            "award_date",
            "period_start",
            "period_end",
            "published_at",
            "event_at",
        ):
            value = payload.get(key)
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
        return payload
