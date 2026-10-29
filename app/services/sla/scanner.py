from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import (
    ColumnElement,
    DateTime,
    Float,
    Integer,
    Select,
    and_,
    case,
    cast,
    exists,
    func,
    literal,
    null,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import Priority
from app.core.events import DomainEvent, EscalationRaised, SlaWarningRaised
from app.models.calendar import SlaMode
from app.models.org import Category, Department
from app.models.sla import EscalationEvent, SlaTimer, TimerKind
from app.models.ticket import Ticket
from app.services.calendar import load_working_calendar, ticket_sla_mode
from app.services.policy import PolicyService
from app.services.sla.due_time import SlaModeName, scaled_hours
from app.services.sla.escalation import CREATION_CONTACT, record_step, resolve_recipients
from app.services.sla.levels import SLA_TIMER_KINDS, is_running, recompute_ticket
from app.services.sla.timers import TERMINAL_STATUSES
from app.services.sla.working_time import WorkingCalendar, working_time
from app.services.workflow.common import AuditEntry, TimelineEntry, Workflow, event_data

SCAN_LOCK_KEY: Final = 7_420_019
BATCH_SIZE: Final = 100
REPEAT_PREFIX: Final = "L3_REPEAT_"


@dataclass(frozen=True, slots=True)
class Step:
    key: str
    level: int


def repeat_index(
    timer: SlaTimer, now: datetime, repeat: timedelta, calendar: WorkingCalendar | None = None
) -> int:
    if timer.l3_at is None or now < timer.l3_at:
        return 0
    if calendar is not None:
        return working_time(calendar, timer.l3_at, now) // repeat
    return int((now - timer.l3_at) / repeat)


def due_steps(
    timer: SlaTimer,
    ticket: Ticket,
    now: datetime,
    repeat: timedelta,
    calendar: WorkingCalendar | None = None,
) -> list[Step]:
    steps: list[Step] = []
    if timer.kind is TimerKind.INITIAL_RESPONSE and ticket.priority is Priority.CRITICAL:
        steps.append(Step(CREATION_CONTACT, 1))
    if timer.warning_at is not None and now >= timer.warning_at:
        steps.append(Step("L1", 1))
    if now >= timer.due_at:
        steps.append(Step("L2", 2))
    if timer.l3_at is not None and now >= timer.l3_at:
        steps.append(Step("L3", 3))
        index = repeat_index(timer, now, repeat, calendar)
        if index >= 1:
            steps.append(Step(f"{REPEAT_PREFIX}{index}", 3))
    return steps


def steps_to_emit(new_steps: Sequence[Step]) -> list[Step]:
    contact = [step for step in new_steps if step.key == CREATION_CONTACT]
    latest: dict[int, Step] = {}
    for step in new_steps:
        if step.key != CREATION_CONTACT:
            latest[step.level] = step
    return [*contact, *(latest[level] for level in sorted(latest))]


def step_detail(timer_kind: TimerKind, step: Step) -> str:
    label = timer_kind.value.replace("_", " ")
    if step.key == CREATION_CONTACT:
        return "Escalation contact notified of a critical ticket"
    if step.level == 1:
        return f"L1 {label} warning"
    return f"L{step.level} {label} breach"


def _recorded(key: ColumnElement[str]) -> ColumnElement[bool]:
    return exists().where(
        EscalationEvent.ticket_id == SlaTimer.ticket_id,
        EscalationEvent.timer_kind == SlaTimer.kind,
        EscalationEvent.cycle == SlaTimer.cycle,
        EscalationEvent.step_key == key,
    )


def business_basis(policy_mode: SlaModeName) -> ColumnElement[bool]:
    return case(
        (Category.sla_mode.is_not(None), Category.sla_mode == SlaMode.BUSINESS),
        (Department.sla_mode.is_not(None), Department.sla_mode == SlaMode.BUSINESS),
        else_=literal(policy_mode == "business"),
    )


def candidate_timers(
    now: datetime, repeat: timedelta, policy_mode: SlaModeName = "calendar"
) -> Select[tuple[SlaTimer]]:
    at = literal(now, DateTime(timezone=True))
    l3_passed = and_(SlaTimer.l3_at.is_not(None), SlaTimer.l3_at <= at)
    elapsed = case(
        (
            business_basis(policy_mode),
            func.working_seconds(SlaTimer.l3_at, at, type_=Float),
        ),
        else_=func.extract("epoch", at - SlaTimer.l3_at),
    )
    index = cast(func.floor(elapsed / repeat.total_seconds()), Integer)
    current_key = case(
        (and_(l3_passed, index >= 1), func.concat(REPEAT_PREFIX, index)),
        (l3_passed, literal("L3")),
        (SlaTimer.due_at <= at, literal("L2")),
        (and_(SlaTimer.warning_at.is_not(None), SlaTimer.warning_at <= at), literal("L1")),
        else_=null(),
    )
    level_pending = and_(current_key.is_not(None), ~_recorded(current_key))
    contact_pending = and_(
        SlaTimer.kind == TimerKind.INITIAL_RESPONSE,
        Ticket.priority == Priority.CRITICAL,
        ~_recorded(literal(CREATION_CONTACT)),
    )
    return (
        select(SlaTimer)
        .join(Ticket, Ticket.id == SlaTimer.ticket_id)
        .join(Department, Department.id == Ticket.department_id)
        .outerjoin(Category, Category.id == Ticket.category_id)
        .where(
            SlaTimer.kind.in_(sorted(SLA_TIMER_KINDS)),
            SlaTimer.met_at.is_(None),
            SlaTimer.stopped_at.is_(None),
            SlaTimer.paused_at.is_(None),
            Ticket.status.not_in(sorted(TERMINAL_STATUSES)),
            or_(level_pending, contact_pending),
        )
        .order_by(SlaTimer.due_at, SlaTimer.id)
    )


class SlaScanner:
    def __init__(self, session: Session, clock: Clock, scale: float) -> None:
        self._session = session
        self._clock = clock
        self._scale = scale
        self._flow = Workflow(session, clock)
        self._calendar: WorkingCalendar | None = None
        self._policy_mode: SlaModeName = "calendar"

    def run(self) -> int:
        locked = self._session.scalar(select(func.pg_try_advisory_xact_lock(SCAN_LOCK_KEY)))
        if not locked:
            return 0
        now = self._clock.now()
        policy = PolicyService(self._session).current()
        self._policy_mode = policy.sla_mode
        repeat = scaled_hours(policy.escalation_repeat_hours, self._scale)
        statement = (
            candidate_timers(now, repeat, policy.sla_mode)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True, of=SlaTimer)
            .execution_options(populate_existing=True)
        )
        timers = list(self._session.scalars(statement))
        processed = 0
        for timer in timers:
            with self._session.begin_nested():
                if self._process(timer, now, repeat):
                    processed += 1
        return processed

    def _process(self, timer: SlaTimer, now: datetime, repeat: timedelta) -> bool:
        ticket = self._session.scalars(
            select(Ticket)
            .where(Ticket.id == timer.ticket_id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        ).first()
        if ticket is None or ticket.status in TERMINAL_STATUSES or not is_running(timer):
            return False
        new_steps = [
            step
            for step in due_steps(timer, ticket, now, repeat, self._repeat_calendar(ticket))
            if self._record(ticket, timer, step, now)
        ]
        if not new_steps:
            return False
        recompute_ticket(self._session, self._clock, ticket)
        events: list[DomainEvent] = []
        for step in steps_to_emit(new_steps):
            self._flow.record(
                ticket,
                None,
                now,
                TimelineEntry(
                    action="escalation",
                    detail=step_detail(timer.kind, step),
                    public=False,
                    data=event_data(
                        timer_kind=timer.kind,
                        cycle=timer.cycle,
                        level=step.level,
                        step_key=step.key,
                    ),
                ),
                AuditEntry(
                    action="ticket_escalation",
                    new_value={
                        "timer_kind": timer.kind,
                        "cycle": timer.cycle,
                        "level": step.level,
                        "step_key": step.key,
                    },
                ),
            )
            events.append(self._event(ticket, timer, step, now))
        self._flow.publish(*events)
        return True

    def _repeat_calendar(self, ticket: Ticket) -> WorkingCalendar | None:
        if ticket_sla_mode(self._session, ticket, self._policy_mode) != "business":
            return None
        if self._calendar is None:
            self._calendar = load_working_calendar(self._session)
        return self._calendar

    def _record(self, ticket: Ticket, timer: SlaTimer, step: Step, now: datetime) -> bool:
        recipients = resolve_recipients(
            self._session, ticket, step.level, creation_contact=step.key == CREATION_CONTACT
        )
        return record_step(
            self._session,
            ticket,
            timer.kind,
            timer.cycle,
            step.level,
            step.key,
            now,
            [user.id for user in recipients],
        )

    @staticmethod
    def _event(ticket: Ticket, timer: SlaTimer, step: Step, now: datetime) -> DomainEvent:
        if step.level == 1 and step.key != CREATION_CONTACT:
            return SlaWarningRaised(
                actor_id=None,
                occurred_at=now,
                ticket_id=ticket.id,
                timer_kind=timer.kind,
                level=step.level,
            )
        return EscalationRaised(
            actor_id=None,
            occurred_at=now,
            ticket_id=ticket.id,
            timer_kind=timer.kind,
            level=step.level,
            step_key=step.key,
        )
