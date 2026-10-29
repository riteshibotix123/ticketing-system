import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UuidPk, enum_type
from app.models.calendar import SlaMode


class Department(Timestamps, Base):
    __tablename__ = "departments"
    __table_args__ = (CheckConstraint("id ~ '^[A-Z]{2,6}$'", name="code_format"),)

    id: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    escalation_contact_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", use_alter=True), nullable=True, index=True
    )
    sla_mode: Mapped[SlaMode | None] = mapped_column(
        enum_type(SlaMode, "department_sla_mode"), nullable=True
    )


class SpokeAssignment(UuidPk, Base):
    __tablename__ = "spoke_assignments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    department_id: Mapped[str] = mapped_column(
        String(6), ForeignKey("departments.id"), nullable=False, index=True
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Category(UuidPk, Timestamps, Base):
    __tablename__ = "categories"

    department_id: Mapped[str] = mapped_column(
        String(6), ForeignKey("departments.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_confidential: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    sla_mode: Mapped[SlaMode | None] = mapped_column(
        enum_type(SlaMode, "category_sla_mode"), nullable=True
    )


class ConfidentialGrant(UuidPk, Base):
    __tablename__ = "confidential_grants"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id"), nullable=False, index=True
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index(
    "uq_spoke_assignments_active",
    SpokeAssignment.user_id,
    SpokeAssignment.department_id,
    unique=True,
    postgresql_where=text("revoked_at IS NULL"),
)
Index(
    "uq_categories_department_id_lower_name",
    Category.department_id,
    func.lower(Category.name),
    unique=True,
)
Index(
    "uq_confidential_grants_active",
    ConfidentialGrant.user_id,
    ConfidentialGrant.category_id,
    unique=True,
    postgresql_where=text("revoked_at IS NULL"),
)
