import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import ColumnElement, Select, or_, select

from app.models.audit import AuditLog
from app.models.ticket import Ticket
from app.policy import Actor
from app.policy.visibility import visible_ticket_clause

LIKE_ESCAPE: Final = "\\"


@dataclass(frozen=True, slots=True)
class AuditFilters:
    q: str | None = None
    actor_id: uuid.UUID | None = None
    action: str | None = None
    ticket_no: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


def _escape_like(term: str) -> str:
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def audit_scope(actor: Actor) -> list[ColumnElement[bool]]:
    if actor.is_super_admin:
        return []
    return [
        AuditLog.is_security_limited.is_(False),
        or_(AuditLog.ticket_id.is_(None), visible_ticket_clause(actor)),
    ]


def filter_clauses(filters: AuditFilters) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = []
    term = filters.q.strip() if filters.q else ""
    if term:
        pattern = f"%{_escape_like(term)}%"
        clauses.append(
            or_(
                AuditLog.action.ilike(pattern, escape=LIKE_ESCAPE),
                AuditLog.detail.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    if filters.actor_id is not None:
        clauses.append(AuditLog.actor_id == filters.actor_id)
    if filters.action:
        clauses.append(AuditLog.action == filters.action)
    if filters.ticket_no:
        clauses.append(Ticket.ticket_no == filters.ticket_no)
    if filters.created_from is not None:
        clauses.append(AuditLog.created_at >= filters.created_from)
    if filters.created_to is not None:
        clauses.append(AuditLog.created_at <= filters.created_to)
    return clauses


def audit_statement(actor: Actor, filters: AuditFilters) -> Select[tuple[AuditLog]]:
    return (
        select(AuditLog)
        .outerjoin(Ticket, Ticket.id == AuditLog.ticket_id)
        .where(*audit_scope(actor), *filter_clauses(filters))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )
