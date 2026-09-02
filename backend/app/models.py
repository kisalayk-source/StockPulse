from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    research_llm_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    credentials: Mapped[list["AlpacaCredential"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AlpacaCredential(Base):
    __tablename__ = "alpaca_credentials"
    __table_args__ = (UniqueConstraint("user_id", "mode", name="uq_user_mode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="credentials")


# SEC EDGAR models (imported for metadata registration)
from app.sec.db_models import (  # noqa: E402,F401
    AccumulationEvent,
    AccumulationScore,
    BeneficialOwnership,
    InsiderTransaction,
    InstitutionalHolding,
    InstitutionalPositionChange,
    SecCompanyMapping,
    SecFiling,
)
