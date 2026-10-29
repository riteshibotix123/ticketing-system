import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import JsonObject
from app.models.base import Base, UuidPk


class PolicyVersion(UuidPk, Base):
    __tablename__ = "policy_versions"
    __table_args__ = (CheckConstraint("version >= 1", name="version_positive"),)

    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    config: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
