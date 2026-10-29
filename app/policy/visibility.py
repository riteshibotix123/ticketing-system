from sqlalchemy import ColumnElement, and_, exists, false, or_, select, true
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.models.org import ConfidentialGrant, Department
from app.models.ticket import Ticket, TicketCollaborator
from app.policy import Actor
from app.policy.relationships import ActorContext, load_relationship


def is_visible(ctx: ActorContext, confidential: bool) -> bool:
    if ctx.is_super_admin or ctx.is_requester or ctx.is_assignee or ctx.is_collaborator:
        return True
    if confidential:
        return ctx.has_grant
    return ctx.is_department_spoke or ctx.is_escalation_contact or ctx.is_admin


def can_view_ticket(session: Session, actor: Actor, ticket: Ticket) -> bool:
    return is_visible(load_relationship(session, actor, ticket), ticket.confidential)


def visible_ticket_clause(actor: Actor) -> ColumnElement[bool]:
    if actor.is_super_admin:
        return true()
    collaborator = exists().where(
        TicketCollaborator.ticket_id == Ticket.id,
        TicketCollaborator.user_id == actor.id,
    )
    granted = exists().where(
        ConfidentialGrant.category_id == Ticket.category_id,
        ConfidentialGrant.user_id == actor.id,
        ConfidentialGrant.revoked_at.is_(None),
    )
    not_confidential = Ticket.confidential.is_(False)
    spoke = (
        and_(not_confidential, Ticket.department_id.in_(sorted(actor.spoke_department_ids)))
        if actor.spoke_department_ids
        else false()
    )
    contact_of = select(Department.id).where(Department.escalation_contact_user_id == actor.id)
    contact = and_(not_confidential, Ticket.department_id.in_(contact_of))
    admin = not_confidential if actor.global_role is Role.ADMIN else false()
    return or_(
        Ticket.requester_id == actor.id,
        Ticket.assignee_id == actor.id,
        collaborator,
        spoke,
        contact,
        admin,
        and_(Ticket.confidential.is_(True), granted),
    )
