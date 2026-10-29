from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import IST, FrozenClock
from app.core.config import Settings
from app.core.enums import Role
from app.core.events import TicketCreated, publish
from app.integrations.email import InMemorySender
from app.models import (
    Category,
    Department,
    EscalationEvent,
    SlaMode,
    SlaTimer,
    Ticket,
    TimerKind,
    User,
)
from app.policy import Actor
from app.policy.actors import load_actor
from app.schemas.calendar import CalendarBody, HolidayBody
from app.services.calendar import CalendarService, load_working_calendar, resolve_sla_mode
from app.services.handlers import register_all
from app.services.policy import PolicyService
from app.services.sla.due_time import SlaModeName
from app.services.sla.scanner import candidate_timers
from app.services.sla.timers import Timers
from app.services.sla.working_time import working_time
from app.worker import JobContext
from app.worker.jobs import sla_scan
from tests.factories import (
    FACTORY_NOW,
    make_category,
    make_department,
    make_policy_version,
    make_ticket,
    make_user,
)

T0 = FACTORY_NOW
H = timedelta(hours=1)


def ist(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=IST)


@dataclass(frozen=True)
class Desk:
    it: Department
    requester: User
    super_admin: Actor


@pytest.fixture(autouse=True)
def handlers() -> None:
    register_all()


@pytest.fixture
def desk(db: Session) -> Desk:
    it = make_department(db, "IT")
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    actor = load_actor(db, super_admin.id)
    assert actor is not None
    return Desk(it=it, requester=make_user(db, it), super_admin=actor)


@pytest.fixture
def context(clock: FrozenClock, settings: Settings) -> JobContext:
    return JobContext(clock=clock, settings=settings, sender=InMemorySender())


def new_ticket(db: Session, desk: Desk, category: Category | None = None) -> Ticket:
    ticket = make_ticket(db, desk.requester, desk.it, category=category)
    publish(db, TicketCreated(actor_id=desk.requester.id, occurred_at=T0, ticket_id=ticket.id))
    db.flush()
    return ticket


def initial(db: Session, ticket: Ticket) -> SlaTimer:
    return db.scalars(
        select(SlaTimer).where(
            SlaTimer.ticket_id == ticket.id, SlaTimer.kind == TimerKind.INITIAL_RESPONSE
        )
    ).one()


def set_policy_mode(db: Session, mode: SlaModeName) -> None:
    current = PolicyService(db).current_version()
    make_policy_version(db, current.version + 1, {**current.config, "sla_mode": mode})


def step_keys(db: Session, ticket: Ticket) -> list[str]:
    rows = db.scalars(
        select(EscalationEvent.step_key)
        .where(EscalationEvent.ticket_id == ticket.id)
        .order_by(EscalationEvent.at, EscalationEvent.step_key)
    )
    return list(rows)


def scan_at(db: Session, clock: FrozenClock, context: JobContext, at: datetime) -> int:
    clock.set(at)
    return sla_scan.run(db, context)


@pytest.mark.parametrize(
    ("category", "department", "policy", "expected"),
    [
        (SlaMode.CALENDAR, SlaMode.BUSINESS, "business", "calendar"),
        (SlaMode.BUSINESS, SlaMode.CALENDAR, "calendar", "business"),
        (None, SlaMode.BUSINESS, "calendar", "business"),
        (None, SlaMode.CALENDAR, "business", "calendar"),
        (None, None, "business", "business"),
        (None, None, "calendar", "calendar"),
    ],
)
def test_basis_resolution_order(
    category: SlaMode | None, department: SlaMode | None, policy: SlaModeName, expected: str
) -> None:
    assert resolve_sla_mode(category, department, policy) == expected


def test_switching_department_to_business_moves_due_times(db: Session, desk: Desk) -> None:
    calendar_timer = initial(db, new_ticket(db, desk))
    assert calendar_timer.due_at == T0 + 24 * H
    assert calendar_timer.warning_at == T0 + 18 * H
    desk.it.sla_mode = SlaMode.BUSINESS
    db.flush()
    business_timer = initial(db, new_ticket(db, desk))
    assert business_timer.warning_at == ist(29, 10)
    assert business_timer.due_at == ist(29, 16)
    assert business_timer.l3_at == ist(3, 13, month=11)


def test_overrides_and_policy_mode_choose_the_basis(db: Session, desk: Desk) -> None:
    desk.it.sla_mode = SlaMode.BUSINESS
    office = make_category(db, desk.it, "Office")
    office.sla_mode = SlaMode.CALENDAR
    db.flush()
    assert initial(db, new_ticket(db, desk, office)).due_at == T0 + 24 * H
    assert initial(db, new_ticket(db, desk, make_category(db, desk.it))).due_at == ist(29, 16)
    desk.it.sla_mode = None
    set_policy_mode(db, "business")
    db.flush()
    assert initial(db, new_ticket(db, desk)).due_at == ist(29, 16)
    desk.it.sla_mode = SlaMode.CALENDAR
    db.flush()
    assert initial(db, new_ticket(db, desk)).due_at == T0 + 24 * H


def test_calendar_changes_apply_from_the_next_timer_start(
    db: Session, desk: Desk, clock: FrozenClock
) -> None:
    desk.it.sla_mode = SlaMode.BUSINESS
    db.flush()
    first = new_ticket(db, desk)
    service = CalendarService(db, clock)
    service.add_holiday(desk.super_admin, HolidayBody(date="2026-10-28", name="Office closed"))
    service.update(
        desk.super_admin,
        CalendarBody(working_days=[1, 2, 3, 4], work_start="10:00", work_end="17:00"),
    )
    db.expire_all()
    assert initial(db, first).due_at == ist(29, 16)
    second = initial(db, new_ticket(db, desk))
    assert second.due_at == ist(3, 13, month=11)


def test_auto_close_skips_holidays_in_calendar_mode(
    db: Session, desk: Desk, clock: FrozenClock
) -> None:
    CalendarService(db, clock).add_holiday(
        desk.super_admin, HolidayBody(date="2026-11-02", name="Bank holiday")
    )
    ticket = new_ticket(db, desk)
    timers = Timers(db, ticket, PolicyService(db).current(), 1.0)
    assert timers.mode == "calendar"
    timer = timers.start_auto_close(ist(30, 10))
    assert timer is not None
    assert timer.due_at == ist(5, 10, month=11)


def test_working_seconds_function_matches_python(
    db: Session, desk: Desk, clock: FrozenClock
) -> None:
    pairs = [
        (ist(27, 10), ist(27, 14)),
        (ist(27, 10), ist(29, 16)),
        (ist(30, 16), ist(3, 11, month=11)),
        (ist(27, 19), ist(28, 8)),
        (ist(28, 10), ist(27, 10)),
        (ist(1, 0, month=10), ist(15, 12, month=11)),
    ]

    def compare() -> None:
        calendar = load_working_calendar(db)
        for start, end in pairs:
            expected = working_time(calendar, start, end).total_seconds()
            actual = db.scalar(select(func.working_seconds(start, end)))
            assert actual == pytest.approx(expected), (start, end)

    compare()
    service = CalendarService(db, clock)
    service.update(
        desk.super_admin,
        CalendarBody(working_days=[1, 2, 3, 4, 5, 6], work_start="10:00", work_end="17:30"),
    )
    service.add_holiday(desk.super_admin, HolidayBody(date="2026-11-02", name="Bank holiday"))
    compare()


def test_business_repeat_steps_count_working_time(
    db: Session, desk: Desk, clock: FrozenClock, context: JobContext
) -> None:
    desk.it.sla_mode = SlaMode.BUSINESS
    db.flush()
    ticket = new_ticket(db, desk)
    scan_at(db, clock, context, ist(3, 13, month=11))
    assert step_keys(db, ticket) == ["L1", "L2", "L3"]
    quiet = ist(4, 13, month=11)
    assert db.scalars(candidate_timers(quiet.astimezone(UTC), 24 * H)).all() == []
    assert scan_at(db, clock, context, quiet) == 0
    assert scan_at(db, clock, context, ist(6, 9, 30, month=11)) == 0
    assert scan_at(db, clock, context, ist(6, 10, 30, month=11)) == 1
    assert step_keys(db, ticket) == ["L1", "L2", "L3", "L3_REPEAT_1"]
