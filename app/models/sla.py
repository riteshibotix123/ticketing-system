import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UuidPk, enum_type


class TimerKind(StrEnum):
    INITIAL_RESPONSE = "initial_response"
    PROGRESS_UPDATE = "progress_update"
    ETA = "eta"
    AUTO_CLOSE = "auto_close"
    REQUESTER_REMINDER = "requester_reminder"
    HOLD_REVIEW = "hold_review"


class SlaTimer(UuidPk, Base):
    __tablename__ = "sla_timers"
    __table_args__ = (
        UniqueConstraint("ticket_id", "kind"),
        CheckConstraint("cycle >= 1", name="cycle_positive"),
        CheckConstraint("paused_seconds >= 0", name="paused_seconds_non_negative"),
        CheckConstraint("level BETWEEN 0 AND 3", name="level_range"),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id"), nullable=False)
    kind: Mapped[TimerKind] = mapped_column(enum_type(TimerKind, "timer_kind"), nullable=False)
    cycle: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    warning_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    l3_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    level: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EscalationEvent(UuidPk, Base):
    __tablename__ = "escalation_events"
    __table_args__ = (
        UniqueConstraint("ticket_id", "timer_kind", "cycle", "step_key"),
        CheckConstraint("cycle >= 1", name="cycle_positive"),
        CheckConstraint("level BETWEEN 1 AND 3", name="level_range"),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id"), nullable=False)
    timer_kind: Mapped[TimerKind] = mapped_column(
        enum_type(TimerKind, "escalation_timer_kind"), nullable=False
    )
    cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recipient_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), nullable=False, default=list, server_default=text("'{}'")
    )


Index(
    "ix_sla_timers_active_due_at",
    SlaTimer.due_at,
    postgresql_where=text("met_at IS NULL AND stopped_at IS NULL AND paused_at IS NULL"),
)
Index("ix_escalation_events_at", EscalationEvent.at)
