"""SQLAlchemy models for government contract events and mappings."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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


class GovernmentEvent(Base):
    __tablename__ = "government_events"
    __table_args__ = (
        UniqueConstraint("source", "event_id", name="uq_gov_source_event"),
        Index("ix_gov_ticker_event_at", "ticker", "event_at"),
        Index("ix_gov_uei", "uei"),
        Index("ix_gov_cage", "cage"),
        Index("ix_gov_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)

    contract_number: Mapped[str | None] = mapped_column(String(128), index=True)
    solicitation_number: Mapped[str | None] = mapped_column(String(128), index=True)

    company_name: Mapped[str | None] = mapped_column(String(512))
    parent_company: Mapped[str | None] = mapped_column(String(512))
    uei: Mapped[str | None] = mapped_column(String(32))
    cage: Mapped[str | None] = mapped_column(String(16))
    ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    cik: Mapped[str | None] = mapped_column(String(10), index=True)
    mapping_confidence: Mapped[float | None] = mapped_column(Float)

    agency: Mapped[str | None] = mapped_column(String(256))
    sub_agency: Mapped[str | None] = mapped_column(String(256))
    title: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)
    naics: Mapped[str | None] = mapped_column(String(16))
    psc: Mapped[str | None] = mapped_column(String(16))
    contract_type: Mapped[str | None] = mapped_column(String(64))

    estimated_value: Mapped[float | None] = mapped_column(Float)
    ceiling_amount: Mapped[float | None] = mapped_column(Float)
    awarded_amount: Mapped[float | None] = mapped_column(Float)
    obligated_amount: Mapped[float | None] = mapped_column(Float)
    transaction_amount: Mapped[float | None] = mapped_column(Float)

    posted_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    award_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    sole_source: Mapped[bool] = mapped_column(Boolean, default=False)
    idiq: Mapped[bool] = mapped_column(Boolean, default=False)
    option_only: Mapped[bool] = mapped_column(Boolean, default=False)

    source_url: Mapped[str | None] = mapped_column(String(1024))
    raw_json: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class GovernmentContract(Base):
    __tablename__ = "government_contracts"
    __table_args__ = (
        UniqueConstraint("contract_number", "ticker", name="uq_gov_contract_ticker"),
        Index("ix_gov_contract_ticker", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    solicitation_number: Mapped[str | None] = mapped_column(String(128))
    ticker: Mapped[str | None] = mapped_column(String(16))
    company_name: Mapped[str | None] = mapped_column(String(512))
    agency: Mapped[str | None] = mapped_column(String(256))
    ceiling_amount: Mapped[float | None] = mapped_column(Float)
    awarded_amount: Mapped[float | None] = mapped_column(Float)
    obligated_amount: Mapped[float | None] = mapped_column(Float)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sole_source: Mapped[bool] = mapped_column(Boolean, default=False)
    idiq: Mapped[bool] = mapped_column(Boolean, default=False)
    incumbent: Mapped[bool] = mapped_column(Boolean, default=False)
    multi_year: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )


class GovernmentCompanyMapping(Base):
    __tablename__ = "government_company_mappings"
    __table_args__ = (
        UniqueConstraint("uei", name="uq_gov_map_uei"),
        UniqueConstraint("cage", name="uq_gov_map_cage"),
        Index("ix_gov_map_ticker", "ticker"),
        Index("ix_gov_map_cik", "cik"),
        Index("ix_gov_map_name", "normalized_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uei: Mapped[str | None] = mapped_column(String(32))
    cage: Mapped[str | None] = mapped_column(String(16))
    cik: Mapped[str | None] = mapped_column(String(10))
    normalized_name: Mapped[str | None] = mapped_column(String(512))
    company_name: Mapped[str | None] = mapped_column(String(512))
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )
