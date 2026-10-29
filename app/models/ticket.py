import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Priority, ScanStatus, TicketStatus
from app.core.types import JsonObject
from app.models.base import Base, Timestamps, UuidPk, enum_type


class CloseReason(StrEnum):
    CONFIRMED = "confirmed"
    ADMIN = "admin"
    AUTO = "auto"


class TicketEventKind(StrEnum):
    COMMENT = "comment"
    INTERNAL_NOTE = "internal_note"
    AUDIT = "audit"


class TicketCounter(Base):
    __tablename__ = "ticket_counters"
    __table_args__ = (
        CheckConstraint("department_code ~ '^[A-Z]{2,6}$'", name="department_code_format"),
        CheckConstraint("year BETWEEN 1000 AND 9999", name="year_four_digits"),
        CheckConstraint("last_value >= 0", name="last_value_non_negative"),
    )

    department_code: Mapped[str] = mapped_column(String(6), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class Ticket(UuidPk, Timestamps, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "ticket_no ~ '^IBX-[A-Z]{2,6}-[0-9]{4}-[0-9]{6}$'", name="ticket_no_format"
        ),
        CheckConstraint(
            "origin_department_code ~ '^[A-Z]{2,6}$'", name="origin_department_code_format"
        ),
        CheckConstraint("reopen_count >= 0", name="reopen_count_non_negative"),
        CheckConstraint(
            "feedback_rating IS NULL OR feedback_rating BETWEEN 1 AND 5",
            name="feedback_rating_range",
        ),
        CheckConstraint("escalation_level BETWEEN 0 AND 3", name="escalation_level_range"),
    )

    ticket_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    origin_department_code: Mapped[str] = mapped_column(String(6), nullable=False)
    department_id: Mapped[str] = mapped_column(
        String(6), ForeignKey("departments.id"), nullable=False
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("categories.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requested_priority: Mapped[Priority] = mapped_column(
        enum_type(Priority, "requested_priority"), nullable=False
    )
    priority: Mapped[Priority] = mapped_column(enum_type(Priority, "priority"), nullable=False)
    confidential: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    status: Mapped[TicketStatus] = mapped_column(
        enum_type(TicketStatus, "ticket_status"), nullable=False, default=TicketStatus.NEW
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    sla_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    next_checkpoint_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_team_update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hold_review_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    awaiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[CloseReason | None] = mapped_column(
        enum_type(CloseReason, "close_reason"), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reopen_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    feedback_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_level: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    update_overdue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )


class TicketCollaborator(Base):
    __tablename__ = "ticket_collaborators"

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), primary_key=True, index=True
    )
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TicketEvent(UuidPk, Base):
    __tablename__ = "ticket_events"

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tickets.id"), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    kind: Mapped[TicketEventKind] = mapped_column(
        enum_type(TicketEventKind, "ticket_event_kind"), nullable=False
    )
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    data: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)


class Attachment(UuidPk, Base):
    __tablename__ = "attachments"
    __table_args__ = (CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),)

    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=True, index=True
    )
    uploader_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[ScanStatus] = mapped_column(
        enum_type(ScanStatus, "scan_status"), nullable=False, default=ScanStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index("ix_tickets_department_id_status", Ticket.department_id, Ticket.status)
Index("ix_tickets_escalation_level_priority", Ticket.escalation_level, Ticket.priority)
Index("ix_tickets_updated_at", Ticket.updated_at)
Index(
    "ix_tickets_title_trgm",
    Ticket.title,
    postgresql_using="gin",
    postgresql_ops={"title": "gin_trgm_ops"},
)
Index(
    "ix_tickets_ticket_no_trgm",
    Ticket.ticket_no,
    postgresql_using="gin",
    postgresql_ops={"ticket_no": "gin_trgm_ops"},
)
Index("ix_ticket_events_ticket_id_at", TicketEvent.ticket_id, TicketEvent.at)
Index(
    "ix_ticket_events_kpi_actions",
    TicketEvent.action,
    TicketEvent.at,
    TicketEvent.ticket_id,
    postgresql_where=text("action IN ('acknowledged', 'resolved', 'reopened')"),
)
Index("ix_tickets_created_at", Ticket.created_at)
Index(
    "ix_attachments_unlinked_created_at",
    Attachment.created_at,
    postgresql_where=text("ticket_id IS NULL"),
)
