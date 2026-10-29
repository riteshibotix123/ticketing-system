from datetime import date, time
from typing import Final

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import conflict, forbidden, not_found, validation_error
from app.models.calendar import CALENDAR_ROW_ID, BusinessCalendar, Holiday, SlaMode
from app.models.org import Category, Department
from app.models.ticket import Ticket
from app.policy import Actor
from app.policy.permissions import can_manage_policy, can_read_policy
from app.schemas.calendar import BusinessCalendarOut, CalendarBody, HolidayBody, HolidayOut
from app.services.audit import AuditService
from app.services.policy import PolicyService
from app.services.sla.due_time import SlaModeName
from app.services.sla.working_time import (
    DEFAULT_WORK_END,
    DEFAULT_WORK_START,
    DEFAULT_WORKING_DAYS,
    WorkingCalendar,
)

TIMEZONE: Final = "Asia/Kolkata"
DUPLICATE_HOLIDAY = "A holiday already exists on this date"


def time_text(value: time) -> str:
    return value.strftime("%H:%M")


def resolve_sla_mode(
    category: SlaMode | None, department: SlaMode | None, policy: SlaModeName
) -> SlaModeName:
    for override in (category, department):
        if override is SlaMode.BUSINESS:
            return "business"
        if override is SlaMode.CALENDAR:
            return "calendar"
    return policy


def ticket_sla_mode(session: Session, ticket: Ticket, policy: SlaModeName) -> SlaModeName:
    department = session.get(Department, ticket.department_id)
    category = session.get(Category, ticket.category_id) if ticket.category_id else None
    return resolve_sla_mode(
        category.sla_mode if category is not None else None,
        department.sla_mode if department is not None else None,
        policy,
    )


def active_holidays(session: Session) -> list[Holiday]:
    statement = select(Holiday).where(Holiday.removed_at.is_(None)).order_by(Holiday.holiday_date)
    return list(session.scalars(statement))


def load_working_calendar(session: Session) -> WorkingCalendar:
    row = session.get(BusinessCalendar, CALENDAR_ROW_ID)
    holidays = frozenset(holiday.holiday_date for holiday in active_holidays(session))
    if row is None:
        return WorkingCalendar(holidays=holidays)
    return WorkingCalendar(frozenset(row.working_days), row.work_start, row.work_end, holidays)


class CalendarService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)

    def read(self, actor: Actor) -> BusinessCalendarOut:
        if not can_read_policy(actor):
            raise forbidden()
        return self._out()

    def update(self, actor: Actor, body: CalendarBody) -> BusinessCalendarOut:
        self._require_manager(actor)
        start = time.fromisoformat(body.work_start)
        end = time.fromisoformat(body.work_end)
        if start >= end:
            raise validation_error({"work_end": "Must be after work_start"})
        row = self._lock()
        days = sorted(set(body.working_days))
        old = self._hours(row)
        new: dict[str, object] = {
            "working_days": days,
            "work_start": time_text(start),
            "work_end": time_text(end),
        }
        if new != old:
            row.working_days = days
            row.work_start = start
            row.work_end = end
            self._touch(row, actor)
            self._audit.record(
                action="business_calendar_updated",
                object_type="business_calendar",
                actor_id=actor.id,
                old_value=old,
                new_value=new,
            )
        return self._out()

    def add_holiday(self, actor: Actor, body: HolidayBody) -> BusinessCalendarOut:
        self._require_manager(actor)
        day = date.fromisoformat(body.date)
        row = self._lock()
        if self._active_holiday(day) is not None:
            raise conflict(DUPLICATE_HOLIDAY)
        self._session.add(
            Holiday(
                holiday_date=day,
                name=body.name,
                created_by_id=actor.id,
                created_at=self._clock.now(),
            )
        )
        self._touch(row, actor)
        self._audit.record(
            action="holiday_added",
            object_type="holiday",
            object_id=day.isoformat(),
            actor_id=actor.id,
            new_value={"date": day.isoformat(), "name": body.name},
        )
        return self._out()

    def remove_holiday(self, actor: Actor, holiday_date: str) -> None:
        self._require_manager(actor)
        try:
            day = date.fromisoformat(holiday_date)
        except ValueError as exc:
            raise not_found() from exc
        row = self._lock()
        holiday = self._active_holiday(day)
        if holiday is None:
            raise not_found()
        holiday.removed_at = self._clock.now()
        holiday.removed_by_id = actor.id
        self._touch(row, actor)
        self._audit.record(
            action="holiday_removed",
            object_type="holiday",
            object_id=day.isoformat(),
            actor_id=actor.id,
            old_value={"date": day.isoformat(), "name": holiday.name},
        )

    def _require_manager(self, actor: Actor) -> None:
        policy = PolicyService(self._session).current()
        if not can_manage_policy(actor, policy.admins_can_manage_departments):
            raise forbidden()

    def _lock(self) -> BusinessCalendar:
        self._session.execute(
            insert(BusinessCalendar)
            .values(
                id=CALENDAR_ROW_ID,
                working_days=sorted(DEFAULT_WORKING_DAYS),
                work_start=DEFAULT_WORK_START,
                work_end=DEFAULT_WORK_END,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        row = self._session.get(
            BusinessCalendar, CALENDAR_ROW_ID, with_for_update=True, populate_existing=True
        )
        if row is None:
            raise LookupError("business calendar row is missing")
        return row

    def _touch(self, row: BusinessCalendar, actor: Actor) -> None:
        row.updated_at = self._clock.now()
        row.updated_by_id = actor.id
        self._session.flush()

    def _active_holiday(self, day: date) -> Holiday | None:
        statement = (
            select(Holiday)
            .where(Holiday.holiday_date == day, Holiday.removed_at.is_(None))
            .with_for_update()
        )
        return self._session.scalars(statement).first()

    @staticmethod
    def _hours(row: BusinessCalendar) -> dict[str, object]:
        return {
            "working_days": sorted(row.working_days),
            "work_start": time_text(row.work_start),
            "work_end": time_text(row.work_end),
        }

    def _out(self) -> BusinessCalendarOut:
        row = self._session.get(BusinessCalendar, CALENDAR_ROW_ID)
        calendar = load_working_calendar(self._session)
        return BusinessCalendarOut(
            timezone=TIMEZONE,
            working_days=sorted(calendar.working_days),
            work_start=time_text(calendar.work_start),
            work_end=time_text(calendar.work_end),
            holidays=[
                HolidayOut(date=holiday.holiday_date.isoformat(), name=holiday.name)
                for holiday in active_holidays(self._session)
            ],
            updated_at=row.updated_at if row is not None else None,
        )
