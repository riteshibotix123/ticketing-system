import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import JsonValue
from app.models.base import Base, UuidPk


class AuditLog(UuidPk, Base):
    __tablename__ = "audit_log"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    old_value: Mapped[JsonValue] = mapped_column(JSONB(none_as_null=True), nullable=True)
    new_value: Mapped[JsonValue] = mapped_column(JSONB(none_as_null=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tickets.id"), nullable=True, index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(6), ForeignKey("departments.id"), nullable=True, index=True
    )
    is_security_limited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_confidential_ticket: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )


Index("ix_audit_log_created_at", AuditLog.created_at)
Index("ix_audit_log_object_type_object_id", AuditLog.object_type, AuditLog.object_id)
