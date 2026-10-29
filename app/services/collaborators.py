import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import AccountState, TicketAction
from app.core.errors import conflict, not_found, validation_error
from app.core.events import CollaboratorChanged
from app.models.identity import User
from app.models.ticket import Ticket, TicketCollaborator, TicketEvent, TicketEventKind
from app.policy import Actor
from app.schemas.tickets import CollaboratorBody, TicketOut
from app.services.audit import AuditService
from app.services.workflow.common import TICKET_OBJECT, Workflow, event_data


class CollaboratorService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._flow = Workflow(session, clock)
        self._audit = AuditService(session, clock)

    def add(self, actor: Actor, ticket_no: str, body: CollaboratorBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.MANAGE_COLLABORATORS)
        user = self._target(body.user_id)
        if user.id == ticket.requester_id:
            raise validation_error({"user_id": "The requester cannot be a collaborator"})
        if self._session.get(TicketCollaborator, (ticket.id, user.id)) is not None:
            raise conflict("This user is already a collaborator")
        self._session.add(
            TicketCollaborator(
                ticket_id=ticket.id, user_id=user.id, added_by_id=actor.id, added_at=now
            )
        )
        self._record(ticket, actor, user, now, added=True)
        return self._flow.respond(actor, ticket)

    def remove(self, actor: Actor, ticket_no: str, user_id: str) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.MANAGE_COLLABORATORS)
        try:
            target_id = uuid.UUID(user_id)
        except ValueError as exc:
            raise not_found() from exc
        row = self._session.get(TicketCollaborator, (ticket.id, target_id))
        user = self._session.get(User, target_id)
        if row is None or user is None:
            raise not_found()
        self._session.delete(row)
        self._record(ticket, actor, user, now, added=False)
        return self._flow.respond(actor, ticket)

    def _target(self, user_id: str) -> User:
        try:
            target_id = uuid.UUID(user_id)
        except ValueError as exc:
            raise validation_error({"user_id": "Choose an active user"}) from exc
        user = self._session.get(User, target_id)
        if user is None or user.state is not AccountState.ACTIVE:
            raise validation_error({"user_id": "Choose an active user"})
        return user

    def _record(
        self, ticket: Ticket, actor: Actor, user: User, now: datetime, *, added: bool
    ) -> None:
        action = "collaborator_added" if added else "collaborator_removed"
        detail = (
            f"{user.name} added as a collaborator"
            if added
            else f"{user.name} removed as a collaborator"
        )
        self._session.add(
            TicketEvent(
                ticket_id=ticket.id,
                at=now,
                actor_id=actor.id,
                kind=TicketEventKind.AUDIT,
                action=action,
                detail=detail,
                is_public=False,
                data=event_data(user_id=user.id),
            )
        )
        ticket.updated_at = now
        self._audit.record(
            action=f"ticket_{action}",
            object_type=TICKET_OBJECT,
            object_id=ticket.ticket_no,
            actor_id=actor.id,
            old_value=None if added else {"collaborator_id": user.id},
            new_value={"collaborator_id": user.id} if added else None,
            ticket_id=ticket.id,
            department_id=ticket.department_id,
            is_security_limited=ticket.confidential,
            is_confidential_ticket=ticket.confidential,
        )
        self._flow.publish(
            CollaboratorChanged(
                actor_id=actor.id,
                occurred_at=now,
                ticket_id=ticket.id,
                user_id=user.id,
                added=added,
            )
        )
