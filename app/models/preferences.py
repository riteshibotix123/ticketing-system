import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UuidPk, enum_type

DEFAULT_DIGEST_HOUR = 9


class NonCriticalEmail(StrEnum):
    IMMEDIATE = "immediate"
    DAILY_DIGEST = "daily_digest"
    OFF = "off"


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (CheckConstraint("digest_hour BETWEEN 0 AND 23", name="digest_hour_range"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    non_critical_email: Mapped[NonCriticalEmail] = mapped_column(
        enum_type(NonCriticalEmail, "non_critical_email"), nullable=False
    )
    digest_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationDigest(UuidPk, Base):
    __tablename__ = "notification_digests"
    __table_args__ = (UniqueConstraint("user_id", "digest_date"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DigestItem(UuidPk, Base):
    __tablename__ = "digest_items"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("notifications.id"), nullable=False, unique=True
    )
    digest_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("notification_digests.id"), nullable=True, index=True
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dropped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index(
    "ix_digest_items_pending",
    DigestItem.user_id,
    DigestItem.queued_at,
    postgresql_where=text("sent_at IS NULL AND dropped_at IS NULL"),
)
