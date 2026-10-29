import uuid
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.models.org import ConfidentialGrant, Department
from app.models.ticket import Ticket, TicketCollaborator
from app.policy import Actor


@dataclass(frozen=True, slots=True)
class ActorContext:
    actor: Actor
    is_requester: bool
    is_owner: bool
    is_assignee: bool
    is_collaborator: bool
    is_department_spoke: bool
    is_escalation_contact: bool
    has_grant: bool
    is_admin: bool
    is_super_admin: bool

    @property
    def has_confidential_access(self) -> bool:
        return self.is_super_admin or self.has_grant


def relationship_from(
    actor: Actor,
    ticket: Ticket,
    collaborator_ids: Collection[uuid.UUID],
    granted_category_ids: Collection[uuid.UUID],
    contact_department_ids: Collection[str],
) -> ActorContext:
    return ActorContext(
        actor=actor,
        is_requester=ticket.requester_id == actor.id,
        is_owner=ticket.owner_id is not None and ticket.owner_id == actor.id,
        is_assignee=ticket.assignee_id is not None and ticket.assignee_id == actor.id,
        is_collaborator=actor.id in collaborator_ids,
        is_department_spoke=ticket.department_id in actor.spoke_department_ids,
        is_escalation_contact=ticket.department_id in contact_department_ids,
        has_grant=ticket.category_id is not None and ticket.category_id in granted_category_ids,
        is_admin=actor.global_role is Role.ADMIN,
        is_super_admin=actor.is_super_admin,
    )


def is_collaborator(session: Session, actor: Actor, ticket: Ticket) -> bool:
    statement = select(
        exists().where(
            TicketCollaborator.ticket_id == ticket.id,
            TicketCollaborator.user_id == actor.id,
        )
    )
    return bool(session.scalar(statement))


def has_active_grant(session: Session, actor: Actor, category_id: uuid.UUID | None) -> bool:
    if category_id is None:
        return False
    statement = select(
        exists().where(
            ConfidentialGrant.user_id == actor.id,
            ConfidentialGrant.category_id == category_id,
            ConfidentialGrant.revoked_at.is_(None),
        )
    )
    return bool(session.scalar(statement))


def contact_departments(session: Session, actor: Actor) -> frozenset[str]:
    statement = select(Department.id).where(Department.escalation_contact_user_id == actor.id)
    return frozenset(session.scalars(statement))


def load_relationship(session: Session, actor: Actor, ticket: Ticket) -> ActorContext:
    collaborators = {actor.id} if is_collaborator(session, actor, ticket) else set()
    grants = (
        {ticket.category_id}
        if ticket.category_id is not None and has_active_grant(session, actor, ticket.category_id)
        else set()
    )
    return relationship_from(
        actor, ticket, collaborators, grants, contact_departments(session, actor)
    )
