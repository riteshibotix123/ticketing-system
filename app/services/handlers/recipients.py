import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AccountState, Role
from app.models.identity import User
from app.models.ticket import Ticket, TicketCollaborator
from app.policy.actors import load_actor
from app.policy.visibility import can_view_ticket
from app.services.spokes import active_spoke_of


@dataclass(frozen=True, slots=True)
class Recipient:
    user: User
    email: bool


class Recipients:
    def __init__(self, *excluded: uuid.UUID | None) -> None:
        self._excluded = {user_id for user_id in excluded if user_id is not None}
        self._entries: dict[uuid.UUID, Recipient] = {}

    def add(self, users: Iterable[User | None], *, email: bool) -> "Recipients":
        for user in users:
            if user is None or user.id in self._excluded:
                continue
            current = self._entries.get(user.id)
            self._entries[user.id] = Recipient(
                user=user, email=email or (current is not None and current.email)
            )
        return self

    def items(self) -> list[Recipient]:
        return sorted(
            self._entries.values(), key=lambda entry: (entry.user.name, str(entry.user.id))
        )


def active_user(session: Session, user_id: uuid.UUID | None) -> User | None:
    if user_id is None:
        return None
    user = session.get(User, user_id)
    if user is None or user.state is not AccountState.ACTIVE:
        return None
    return user


def active_users_with_roles(session: Session, *roles: Role) -> list[User]:
    statement = select(User).where(
        User.state == AccountState.ACTIVE, User.global_role.in_(list(roles))
    )
    return list(session.scalars(statement))


def department_spokes(session: Session, department_id: str) -> list[User]:
    statement = select(User).where(
        User.state == AccountState.ACTIVE, active_spoke_of(department_id)
    )
    return list(session.scalars(statement))


def collaborators(session: Session, ticket: Ticket) -> list[User]:
    statement = (
        select(User)
        .join(TicketCollaborator, TicketCollaborator.user_id == User.id)
        .where(TicketCollaborator.ticket_id == ticket.id, User.state == AccountState.ACTIVE)
    )
    return list(session.scalars(statement))


def requester(session: Session, ticket: Ticket) -> list[User | None]:
    return [active_user(session, ticket.requester_id)]


def owner_and_assignee(session: Session, ticket: Ticket) -> list[User | None]:
    return [active_user(session, ticket.owner_id), active_user(session, ticket.assignee_id)]


def visible_only(session: Session, ticket: Ticket, entries: Iterable[Recipient]) -> list[Recipient]:
    visible: list[Recipient] = []
    for entry in entries:
        actor = load_actor(session, entry.user.id)
        if actor is not None and can_view_ticket(session, actor, ticket):
            visible.append(entry)
    return visible
