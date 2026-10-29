import uuid
from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Time,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UuidPk

CALENDAR_ROW_ID = 1


class SlaMode(StrEnum):
    CALENDAR = "calendar"
    BUSINESS = "business"


class BusinessCalendar(Base):
    __tablename__ = "business_calendar"
    __table_args__ = (
        CheckConstraint(f"id = {CALENDAR_ROW_ID}", name="single_row"),
        CheckConstraint("work_start < work_end", name="hours_order"),
        CheckConstraint("cardinality(working_days) BETWEEN 1 AND 7", name="working_days_count"),
        CheckConstraint(
            "working_days <@ ARRAY[1,2,3,4,5,6,7]::smallint[]", name="working_days_range"
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    working_days: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    work_start: Mapped[time] = mapped_column(Time, nullable=False)
    work_end: Mapped[time] = mapped_column(Time, nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Holiday(UuidPk, Base):
    __tablename__ = "holidays"

    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index(
    "uq_holidays_active_date",
    Holiday.holiday_date,
    unique=True,
    postgresql_where=text("removed_at IS NULL"),
)
