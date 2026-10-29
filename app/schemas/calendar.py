import datetime as dt
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from app.schemas.common import ApiModel
from app.schemas.org import OrgName

TimeOfDay = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
StrictInt = Annotated[int, Field(strict=True)]
ISO_WEEKDAYS = frozenset(range(1, 8))
DateText = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class HolidayOut(ApiModel):
    date: str
    name: str


class BusinessCalendarOut(ApiModel):
    timezone: Literal["Asia/Kolkata"]
    working_days: list[int]
    work_start: str
    work_end: str
    holidays: list[HolidayOut]
    updated_at: dt.datetime | None


class CalendarBody(ApiModel):
    working_days: Annotated[list[StrictInt], Field(min_length=1, max_length=7)]
    work_start: TimeOfDay
    work_end: TimeOfDay

    @field_validator("working_days")
    @classmethod
    def distinct_days(cls, value: list[int]) -> list[int]:
        if not set(value) <= ISO_WEEKDAYS:
            raise ValueError("Use ISO weekdays 1 (Monday) to 7 (Sunday)")
        if len(set(value)) != len(value):
            raise ValueError("Each working day may appear only once")
        return value


class HolidayBody(ApiModel):
    date: DateText
    name: OrgName

    @field_validator("date")
    @classmethod
    def real_date(cls, value: str) -> str:
        dt.date.fromisoformat(value)
        return value
