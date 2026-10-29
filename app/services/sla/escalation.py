import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import AccountState, Role
from app.models.identity import User
from app.models.org import Department
from app.models.sla import EscalationEvent, TimerKind
from app.models.ticket import Ticket
from app.policy.actors import load_actor
from app.policy.visibility import can_view_ticket
from app.services.spokes import active_spoke_of

CREATION_CONTACT: Final = "CREATION_CONTACT"
MANAGEMENT_ROLES: Final = frozenset({Role.ADMIN, Role.SUPER_ADMIN})


def _active_users_with_role(session: Session, role: Role) -> list[User]:
    statement = select(User).where(User.state == AccountState.ACTIVE, User.global_role == role)
    return list(session.scalars(statement))


def _active_user(session: Session, user_id: uuid.UUID | None) -> User | None:
    if user_id is None:
        return None
    user = session.get(User, user_id)
    if user is None or user.state is not AccountState.ACTIVE:
        return None
    return user


def _department_spokes(session: Session, department_id: str) -> list[User]:
    statement = select(User).where(
        User.state == AccountState.ACTIVE, active_spoke_of(department_id)
    )
    return list(session.scalars(statement))


def _escalation_contact(session: Session, ticket: Ticket) -> User | None:
    department = session.get(Department, ticket.department_id)
    if department is None:
        return None
    return _active_user(session, department.escalation_contact_user_id)


def _unique(users: Iterable[User | None]) -> list[User]:
    seen: dict[uuid.UUID, User] = {}
    for user in users:
        if user is not None and user.id not in seen:
            seen[user.id] = user
    return sorted(seen.values(), key=lambda user: (user.name, str(user.id)))


def _team(session: Session, ticket: Ticket) -> list[User | None]:
    return [
        _active_user(session, ticket.owner_id),
        _active_user(session, ticket.assignee_id),
        *_department_spokes(session, ticket.department_id),
    ]


def _contact_or_fallback(session: Session, ticket: Ticket) -> list[User]:
    contact = _escalation_contact(session, ticket)
    if contact is not None:
        return [contact]
    admins = _active_users_with_role(session, Role.ADMIN)
    if admins:
        return admins
    return _active_users_with_role(session, Role.SUPER_ADMIN)


def _candidates(session: Session, ticket: Ticket, level: int, creation_contact: bool) -> list[User]:
    if creation_contact:
        return _unique(_contact_or_fallback(session, ticket))
    if level >= 3:
        return _unique(
            [
                *_active_users_with_role(session, Role.SUPER_ADMIN),
                *_active_users_with_role(session, Role.ADMIN),
            ]
        )
    team = _team(session, ticket)
    if level <= 1:
        return _unique(team)
    contact = _escalation_contact(session, ticket)
    admins = _active_users_with_role(session, Role.ADMIN)
    fallback = (
        _active_users_with_role(session, Role.SUPER_ADMIN) if contact is None and not admins else []
    )
    return _unique([*team, contact, *admins, *fallback])


def _visible_only(session: Session, ticket: Ticket, users: Sequence[User]) -> list[User]:
    visible: list[User] = []
    for user in users:
        actor = load_actor(session, user.id)
        if actor is not None and can_view_ticket(session, actor, ticket):
            visible.append(user)
    return visible


def resolve_recipients(
    session: Session, ticket: Ticket, level: int, *, creation_contact: bool = False
) -> list[User]:
    recipients = _candidates(session, ticket, level, creation_contact)
    if not ticket.confidential:
        return recipients
    recipients = _visible_only(session, ticket, recipients)
    needs_management = creation_contact or level >= 2
    if needs_management and not any(user.global_role in MANAGEMENT_ROLES for user in recipients):
        recipients = _unique([*recipients, *_active_users_with_role(session, Role.SUPER_ADMIN)])
    return recipients


def record_step(
    session: Session,
    ticket: Ticket,
    timer_kind: TimerKind,
    cycle: int,
    level: int,
    step_key: str,
    at: datetime,
    recipient_ids: Sequence[uuid.UUID],
) -> bool:
    statement = (
        insert(EscalationEvent)
        .values(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            timer_kind=timer_kind,
            cycle=cycle,
            level=level,
            step_key=step_key,
            at=at,
            recipient_ids=list(recipient_ids),
        )
        .on_conflict_do_nothing(index_elements=["ticket_id", "timer_kind", "cycle", "step_key"])
        .returning(EscalationEvent.id)
    )
    return session.execute(statement).scalar_one_or_none() is not None
