import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final

from sqlalchemy import (
    ColumnElement,
    Date,
    Float,
    Select,
    Subquery,
    and_,
    cast,
    exists,
    func,
    not_,
    or_,
    select,
    tuple_,
)
from sqlalchemy.orm import InstrumentedAttribute, aliased

from app.core.enums import Priority, TicketStatus
from app.models.org import Category, Department
from app.models.sla import EscalationEvent, SlaTimer, TimerKind
from app.models.ticket import Ticket, TicketEvent
from app.queries.tickets import is_active_ticket
from app.schemas.reports import AgingBucket
from app.services.sla.escalation import CREATION_CONTACT

ACKNOWLEDGED: Final = "acknowledged"
RESOLVED: Final = "resolved"
REOPENED: Final = "reopened"
BREACH_STEP: Final = "L2"
REPEAT_PREFIX: Final = "L3_REPEAT_"
IST_ZONE: Final = "Asia/Kolkata"
UNACKNOWLEDGED_AFTER: Final = timedelta(hours=24)
TOP_CATEGORIES: Final = 10
UNCATEGORISED: Final = "Uncategorised"
PAUSED_STATUSES: Final = (TicketStatus.AWAITING_REQUESTER, TicketStatus.ON_HOLD)
AGING_BUCKETS: Final[tuple[tuple[AgingBucket, int, int | None], ...]] = (
    ("0_2", 0, 3),
    ("3_7", 3, 8),
    ("8_14", 8, 15),
    ("15_30", 15, 31),
    ("31_plus", 31, None),
)

type Scope = Sequence[ColumnElement[bool]]


@dataclass(frozen=True, slots=True)
class Window:
    start: datetime
    end: datetime

    def contains(
        self, column: InstrumentedAttribute[datetime] | ColumnElement[datetime]
    ) -> ColumnElement[bool]:
        return and_(column >= self.start, column < self.end)


def scope_clauses(
    visibility: ColumnElement[bool],
    department_ids: Collection[str] | None,
    priorities: Collection[Priority],
) -> list[ColumnElement[bool]]:
    clauses = [visibility]
    if department_ids is not None:
        clauses.append(Ticket.department_id.in_(sorted(department_ids)))
    if priorities:
        clauses.append(Ticket.priority.in_(sorted(priorities)))
    return clauses


def _first_event(action: str, window: Window) -> Subquery:
    earlier = aliased(TicketEvent)
    return (
        select(TicketEvent.ticket_id.label("ticket_id"), TicketEvent.at.label("at"))
        .where(
            TicketEvent.action == action,
            window.contains(TicketEvent.at),
            ~exists().where(
                earlier.ticket_id == TicketEvent.ticket_id,
                earlier.action == action,
                or_(
                    earlier.at < TicketEvent.at,
                    and_(earlier.at == TicketEvent.at, earlier.id < TicketEvent.id),
                ),
            ),
        )
        .subquery()
    )


def _elapsed(first: Subquery) -> ColumnElement[float]:
    return cast(func.extract("epoch", first.c.at - Ticket.created_at), Float)


def duration_statement(
    scope: Scope, action: str, window: Window
) -> Select[tuple[int, float | None, float | None]]:
    first = _first_event(action, window)
    seconds = _elapsed(first)
    return (
        select(
            func.count(),
            cast(func.avg(seconds), Float),
            cast(func.percentile_cont(0.5).within_group(seconds), Float),
        )
        .select_from(Ticket)
        .join(first, first.c.ticket_id == Ticket.id)
        .where(*scope)
    )


def trend_statement(
    scope: Scope, window: Window
) -> Select[tuple[int, date | None, int, float | None, float | None]]:
    first = _first_event(ACKNOWLEDGED, window)
    inner = (
        select(
            cast(func.timezone(IST_ZONE, first.c.at), Date).label("day"),
            _elapsed(first).label("seconds"),
        )
        .select_from(Ticket)
        .join(first, first.c.ticket_id == Ticket.id)
        .where(*scope)
        .subquery()
    )
    return (
        select(
            func.grouping(inner.c.day),
            inner.c.day,
            func.count(),
            cast(func.avg(inner.c.seconds), Float),
            cast(func.percentile_cont(0.5).within_group(inner.c.seconds), Float),
        )
        .group_by(func.grouping_sets(tuple_(inner.c.day), tuple_()))
        .order_by(inner.c.day)
    )


def sla_statement(scope: Scope, window: Window) -> Select[tuple[str, int, int]]:
    missed = exists().where(
        EscalationEvent.ticket_id == Ticket.id,
        EscalationEvent.timer_kind == TimerKind.INITIAL_RESPONSE,
        EscalationEvent.level >= 2,
    )
    inner = (
        select(
            Ticket.department_id.label("department_id"),
            missed.label("missed"),
            Ticket.acknowledged_at.is_not(None).label("acknowledged"),
        )
        .where(*scope, window.contains(Ticket.created_at))
        .subquery()
    )
    return select(
        inner.c.department_id,
        func.count().filter(inner.c.missed),
        func.count().filter(and_(not_(inner.c.missed), inner.c.acknowledged)),
    ).group_by(inner.c.department_id)


def _event_in(action: str, window: Window) -> ColumnElement[bool]:
    return exists().where(
        TicketEvent.ticket_id == Ticket.id,
        TicketEvent.action == action,
        window.contains(TicketEvent.at),
    )


def reopen_statement(scope: Scope, window: Window) -> Select[tuple[int, int]]:
    inner = (
        select(_event_in(REOPENED, window).label("reopened"))
        .where(*scope, _event_in(RESOLVED, window))
        .subquery()
    )
    return select(func.count(), func.count().filter(inner.c.reopened))


def escalation_statement(scope: Scope, window: Window) -> Select[tuple[int, int]]:
    return (
        select(EscalationEvent.level, func.count())
        .join(Ticket, Ticket.id == EscalationEvent.ticket_id)
        .where(
            *scope,
            window.contains(EscalationEvent.at),
            EscalationEvent.step_key != CREATION_CONTACT,
        )
        .group_by(EscalationEvent.level)
    )


def eta_breach_statement(scope: Scope, window: Window) -> Select[tuple[int]]:
    return (
        select(func.count())
        .select_from(EscalationEvent)
        .join(Ticket, Ticket.id == EscalationEvent.ticket_id)
        .where(
            *scope,
            window.contains(EscalationEvent.at),
            EscalationEvent.timer_kind == TimerKind.ETA,
            EscalationEvent.step_key == BREACH_STEP,
        )
    )


def _age_between(now: datetime, low_days: int, high_days: int | None) -> ColumnElement[bool]:
    newest = Ticket.created_at <= now - timedelta(days=low_days)
    if high_days is None:
        return newest
    return and_(newest, Ticket.created_at > now - timedelta(days=high_days))


def snapshot_statement(scope: Scope, now: datetime) -> Select[tuple[int, ...]]:
    overdue_eta = and_(
        Ticket.status.not_in(PAUSED_STATUSES), Ticket.eta.is_not(None), Ticket.eta < now
    )
    unacknowledged = and_(
        Ticket.status == TicketStatus.NEW,
        Ticket.sla_started_at <= now - UNACKNOWLEDGED_AFTER,
    )
    return select(
        func.count().filter(Ticket.update_overdue.is_(True)),
        func.count().filter(overdue_eta),
        func.count().filter(unacknowledged),
        *(func.count().filter(_age_between(now, low, high)) for _, low, high in AGING_BUCKETS),
    ).where(*scope, is_active_ticket())


def persistent_l3_statement(scope: Scope) -> Select[tuple[int]]:
    repeated = exists().where(
        EscalationEvent.ticket_id == Ticket.id,
        EscalationEvent.step_key.startswith(REPEAT_PREFIX, autoescape=True),
        SlaTimer.ticket_id == EscalationEvent.ticket_id,
        SlaTimer.kind == EscalationEvent.timer_kind,
        SlaTimer.cycle == EscalationEvent.cycle,
        SlaTimer.level == 3,
        SlaTimer.met_at.is_(None),
        SlaTimer.stopped_at.is_(None),
    )
    return (
        select(func.count())
        .select_from(Ticket)
        .where(*scope, is_active_ticket(), Ticket.escalation_level == 3, repeated)
    )


def department_statement(
    scope: Scope,
) -> Select[tuple[str, int, int, int, int, int, int, int, int]]:
    return (
        select(
            Ticket.department_id,
            func.count(),
            func.count().filter(Ticket.priority == Priority.LOW),
            func.count().filter(Ticket.priority == Priority.MEDIUM),
            func.count().filter(Ticket.priority == Priority.HIGH),
            func.count().filter(Ticket.priority == Priority.CRITICAL),
            func.count().filter(Ticket.escalation_level == 0),
            func.count().filter(Ticket.escalation_level == 1),
            func.count().filter(Ticket.escalation_level >= 2),
        )
        .where(*scope, is_active_ticket())
        .group_by(Ticket.department_id)
    )


def workload_statement(
    scope: Scope, column: InstrumentedAttribute[uuid.UUID | None]
) -> Select[tuple[uuid.UUID | None, int, int]]:
    return (
        select(column, func.count(), func.count().filter(Ticket.escalation_level >= 2))
        .where(*scope, is_active_ticket())
        .group_by(column)
    )


def top_categories_statement(
    scope: Scope, window: Window
) -> Select[tuple[uuid.UUID | None, str, int]]:
    total = func.count()
    return (
        select(Ticket.category_id, func.coalesce(Category.name, UNCATEGORISED), total)
        .select_from(Ticket)
        .outerjoin(Category, Category.id == Ticket.category_id)
        .where(*scope, window.contains(Ticket.created_at))
        .group_by(Ticket.category_id, Category.name)
        .order_by(total.desc(), Category.name.asc().nulls_last())
        .limit(TOP_CATEGORIES)
    )


def departments_statement(
    department_ids: Collection[str] | None, requested: str | None
) -> Select[tuple[str, str]]:
    statement = select(Department.id, Department.name).order_by(Department.name, Department.id)
    if requested is not None:
        return statement.where(Department.id == requested)
    statement = statement.where(Department.is_active.is_(True))
    if department_ids is not None:
        statement = statement.where(Department.id.in_(sorted(department_ids)))
    return statement
