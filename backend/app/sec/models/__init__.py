from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class ParsedHolding:
    manager_name: str
    manager_cik: str | None
    issuer_name: str
    issuer_ticker: str | None
    issuer_cusip: str | None
    report_period: date | None
    shares: float
    market_value: float | None
    security_type: str | None = None
    put_call: str | None = None
    voting_authority_sole: float | None = None
    voting_authority_shared: float | None = None


@dataclass
class ParsedBeneficialOwnership:
    reporter_name: str
    reporter_cik: str | None
    issuer_name: str
    issuer_ticker: str | None
    shares: float | None
    ownership_pct: float | None
    form_type: str
    filing_date: date | None
    purpose: str | None = None
    passive_flag: bool = False
    is_amendment: bool = False


@dataclass
class ParsedInsiderTransaction:
    insider_name: str
    insider_title: str | None
    issuer_ticker: str | None
    transaction_date: date | None
    filing_date: date | None
    transaction_code: str
    shares: float
    price: float | None
    value: float | None
    shares_owned_after: float | None
    ownership_type: str | None
    is_derivative: bool = False


@dataclass
class NormalizedEvent:
    event_id: str
    source: str
    accession_number: str
    filing_date: date | None
    reporting_period: date | None
    event_type: str
    component: str
    signal_label: str
    data_timestamp: datetime
    ticker: str
    polarity: float  # -1 to +1 contribution direction
    metadata: dict[str, Any] = field(default_factory=dict)
