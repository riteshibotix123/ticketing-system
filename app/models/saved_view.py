import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import JsonObject
from app.models.base import Base, Timestamps, UuidPk


class SavedView(UuidPk, Timestamps, Base):
    __tablename__ = "saved_views"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    query: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index(
    "uq_saved_views_owner_id_name",
    SavedView.owner_id,
    func.lower(SavedView.name),
    unique=True,
    postgresql_where=text("deleted_at IS NULL"),
)
