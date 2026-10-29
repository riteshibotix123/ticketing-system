import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Final

from sqlalchemy import ColumnElement, Select, case, or_, select, union

from app.core.enums import PRIORITY_RANK, Priority, TicketStatus
from app.models.ticket import Ticket, TicketCollaborator
from app.policy import Actor
from app.policy.visibility import visible_ticket_clause
from app.schemas.tickets import SlaStateFilter

INACTIVE_STATUSES: Final = frozenset(
    {TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED}
)
ACTIVE_STATUSES: Final = frozenset(TicketStatus) - INACTIVE_STATUSES
LIKE_ESCAPE: Final = "\\"


@dataclass(frozen=True, slots=True)
class TicketFilters:
    statuses: frozenset[TicketStatus] = frozenset()
    priorities: frozenset[Priority] = frozenset()
    department_ids: frozenset[str] | None = None
    category_id: uuid.UUID | None = None
    requester_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    sla_state: SlaStateFilter | None = None
    escalation_level: int | None = None
    confidential: bool | None = None
    overdue_eta: bool = False
    unassigned: bool = False
    awaiting_before: datetime | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    q: str | None = None
    extra: Sequence[ColumnElement[bool]] = field(default_factory=tuple)


def priority_rank() -> ColumnElement[int]:
    return case(
        {priority.value: rank for priority, rank in PRIORITY_RANK.items()},
        value=Ticket.priority,
        else_=0,
    )


def is_active_ticket() -> ColumnElement[bool]:
    return Ticket.status.in_(sorted(ACTIVE_STATUSES))


SORTS: Final = MappingProxyType(
    {
        key: key
        for key in (
            "urgency",
            "created_at",
            "-created_at",
            "priority",
            "-priority",
            "status",
            "title",
        )
    }
)
DEFAULT_SORT: Final = "urgency"


def mine_clause(actor: Actor) -> ColumnElement[bool]:
    own = select(Ticket.id).where(Ticket.requester_id == actor.id)
    collaborating = select(TicketCollaborator.ticket_id).where(
        TicketCollaborator.user_id == actor.id
    )
    return Ticket.id.in_(union(own, collaborating))


def assigned_clause(actor: Actor) -> ColumnElement[bool]:
    return Ticket.assignee_id == actor.id


def in_departments(department_ids: Collection[str]) -> ColumnElement[bool]:
    return Ticket.department_id.in_(sorted(department_ids))


def _escape_like(term: str) -> str:
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def _sla_state_clause(state: SlaStateFilter) -> ColumnElement[bool]:
    if state is SlaStateFilter.UNACKNOWLEDGED:
        return Ticket.status == TicketStatus.NEW
    if state is SlaStateFilter.WARNING:
        return Ticket.escalation_level == 1
    if state is SlaStateFilter.BREACHED:
        return Ticket.escalation_level >= 2
    return Ticket.update_overdue.is_(True)


def filter_clauses(filters: TicketFilters, now: datetime) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = list(filters.extra)
    if filters.statuses:
        clauses.append(Ticket.status.in_(sorted(filters.statuses)))
    if filters.priorities:
        clauses.append(Ticket.priority.in_(sorted(filters.priorities)))
    if filters.department_ids is not None:
        clauses.append(in_departments(filters.department_ids))
    if filters.category_id is not None:
        clauses.append(Ticket.category_id == filters.category_id)
    if filters.requester_id is not None:
        clauses.append(Ticket.requester_id == filters.requester_id)
    if filters.assignee_id is not None:
        clauses.append(Ticket.assignee_id == filters.assignee_id)
    if filters.sla_state is not None:
        clauses.append(_sla_state_clause(filters.sla_state))
    if filters.escalation_level is not None:
        clauses.append(Ticket.escalation_level == filters.escalation_level)
    if filters.confidential is not None:
        clauses.append(Ticket.confidential.is_(filters.confidential))
    if filters.overdue_eta:
        clauses.extend([is_active_ticket(), Ticket.eta.is_not(None), Ticket.eta < now])
    if filters.unassigned:
        clauses.append(Ticket.assignee_id.is_(None))
    if filters.awaiting_before is not None:
        clauses.extend(
            [
                Ticket.status == TicketStatus.AWAITING_REQUESTER,
                Ticket.awaiting_since <= filters.awaiting_before,
            ]
        )
    if filters.created_from is not None:
        clauses.append(Ticket.created_at >= filters.created_from)
    if filters.created_to is not None:
        clauses.append(Ticket.created_at <= filters.created_to)
    term = filters.q.strip() if filters.q else ""
    if term:
        pattern = f"%{_escape_like(term)}%"
        clauses.append(
            or_(
                Ticket.ticket_no.ilike(pattern, escape=LIKE_ESCAPE),
                Ticket.title.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    return clauses


def visible_tickets(actor: Actor) -> Select[tuple[Ticket]]:
    return select(Ticket).where(visible_ticket_clause(actor))


def apply_sort(statement: Select[tuple[Ticket]], sort: str) -> Select[tuple[Ticket]]:
    if sort == "created_at":
        return statement.order_by(Ticket.created_at.asc(), Ticket.ticket_no.asc())
    if sort == "-created_at":
        return statement.order_by(Ticket.created_at.desc(), Ticket.ticket_no.asc())
    if sort == "priority":
        return statement.order_by(priority_rank().asc(), Ticket.ticket_no.asc())
    if sort == "-priority":
        return statement.order_by(priority_rank().desc(), Ticket.ticket_no.asc())
    if sort == "status":
        return statement.order_by(Ticket.status.asc(), Ticket.ticket_no.asc())
    if sort == "title":
        return statement.order_by(Ticket.title.asc(), Ticket.ticket_no.asc())
    return statement.order_by(
        case((is_active_ticket(), 0), else_=1),
        Ticket.escalation_level.desc(),
        priority_rank().desc(),
        Ticket.sla_started_at.asc(),
        Ticket.ticket_no.asc(),
    )


def ticket_list_statement(
    actor: Actor, filters: TicketFilters, sort: str, now: datetime
) -> Select[tuple[Ticket]]:
    return apply_sort(visible_tickets(actor).where(*filter_clauses(filters, now)), sort)


def visible_ticket_by_number(actor: Actor, ticket_no: str) -> Select[tuple[Ticket]]:
    return visible_tickets(actor).where(Ticket.ticket_no == ticket_no)
