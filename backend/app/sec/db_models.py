from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SecCompanyMapping(Base):
    __tablename__ = "sec_company_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    cik: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(512))
    exchange: Mapped[str | None] = mapped_column(String(32))
    sic: Mapped[str | None] = mapped_column(String(16))
    sector: Mapped[str | None] = mapped_column(String(128))
    industry: Mapped[str | None] = mapped_column(String(256))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)


class SecFiling(Base):
    __tablename__ = "sec_filings"
    __table_args__ = (UniqueConstraint("accession_number", name="uq_sec_accession"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    cik: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    form_type: Mapped[str] = mapped_column(String(32), nullable=False)
    form_family: Mapped[str] = mapped_column(String(16), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, index=True)
    report_period: Mapped[date | None] = mapped_column(Date)
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False)
    replaces_accession: Mapped[str | None] = mapped_column(String(32))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_metadata: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class InstitutionalHolding(Base):
    __tablename__ = "institutional_holdings"
    __table_args__ = (
        UniqueConstraint(
            "manager_cik",
            "issuer_ticker",
            "report_period",
            "accession_number",
            name="uq_inst_holding",
        ),
        Index("ix_inst_ticker_period", "issuer_ticker", "report_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_number: Mapped[str] = mapped_column(String(32), ForeignKey("sec_filings.accession_number"), nullable=False)
    manager_name: Mapped[str] = mapped_column(String(512), nullable=False)
    manager_cik: Mapped[str | None] = mapped_column(String(10), index=True)
    issuer_name: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer_ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    issuer_cusip: Mapped[str | None] = mapped_column(String(16))
    report_period: Mapped[date | None] = mapped_column(Date)
    shares: Mapped[float] = mapped_column(Float, default=0.0)
    market_value: Mapped[float | None] = mapped_column(Float)
    security_type: Mapped[str | None] = mapped_column(String(64))
    put_call: Mapped[str | None] = mapped_column(String(8))
    portfolio_weight: Mapped[float | None] = mapped_column(Float)


class InstitutionalPositionChange(Base):
    __tablename__ = "institutional_position_changes"
    __table_args__ = (Index("ix_inst_change_ticker", "issuer_ticker", "report_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manager_name: Mapped[str] = mapped_column(String(512), nullable=False)
    manager_cik: Mapped[str | None] = mapped_column(String(10))
    issuer_ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    report_period: Mapped[date | None] = mapped_column(Date)
    previous_shares: Mapped[float] = mapped_column(Float, default=0.0)
    current_shares: Mapped[float] = mapped_column(Float, default=0.0)
    change_shares: Mapped[float] = mapped_column(Float, default=0.0)
    change_pct: Mapped[float | None] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date)


class BeneficialOwnership(Base):
    __tablename__ = "beneficial_ownerships"
    __table_args__ = (Index("ix_beneficial_ticker", "issuer_ticker", "filing_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reporter_name: Mapped[str] = mapped_column(String(512), nullable=False)
    reporter_cik: Mapped[str | None] = mapped_column(String(10))
    issuer_ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    issuer_name: Mapped[str] = mapped_column(String(512), nullable=False)
    shares: Mapped[float | None] = mapped_column(Float)
    ownership_pct: Mapped[float | None] = mapped_column(Float)
    form_type: Mapped[str] = mapped_column(String(32), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date)
    purpose: Mapped[str | None] = mapped_column(Text)
    passive_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str | None] = mapped_column(String(64))


class InsiderTransaction(Base):
    __tablename__ = "insider_transactions"
    __table_args__ = (
        UniqueConstraint("accession_number", "transaction_code", "transaction_date", "insider_name", "shares", name="uq_insider_tx"),
        Index("ix_insider_ticker_date", "issuer_ticker", "transaction_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    insider_name: Mapped[str] = mapped_column(String(512), nullable=False)
    insider_title: Mapped[str | None] = mapped_column(String(256))
    issuer_ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    transaction_date: Mapped[date | None] = mapped_column(Date)
    filing_date: Mapped[date | None] = mapped_column(Date)
    transaction_code: Mapped[str] = mapped_column(String(8), nullable=False)
    normalized_type: Mapped[str] = mapped_column(String(32), nullable=False)
    shares: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float | None] = mapped_column(Float)
    value: Mapped[float | None] = mapped_column(Float)
    shares_owned_after: Mapped[float | None] = mapped_column(Float)
    ownership_type: Mapped[str | None] = mapped_column(String(32))
    is_derivative: Mapped[bool] = mapped_column(Boolean, default=False)


class AccumulationEvent(Base):
    __tablename__ = "accumulation_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_accumulation_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    accession_number: Mapped[str | None] = mapped_column(String(32))
    filing_date: Mapped[date | None] = mapped_column(Date)
    reporting_period: Mapped[date | None] = mapped_column(Date)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    component: Mapped[str] = mapped_column(String(32), nullable=False)
    polarity: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class AccumulationScore(Base):
    __tablename__ = "accumulation_scores"
    __table_args__ = (
        UniqueConstraint("ticker", "score_date", name="uq_accumulation_score_day"),
        Index("ix_accumulation_score_ticker", "ticker", "score_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    signal: Mapped[str] = mapped_column(String(32), nullable=False)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    components_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
