from datetime import datetime
from typing import Final

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import TicketAction, TicketStatus
from app.core.events import (
    CommentAdded,
    DomainEvent,
    TeamUpdateRecorded,
    TicketStatusChanged,
)
from app.models.identity import User
from app.models.ticket import Ticket, TicketEvent, TicketEventKind
from app.policy import Actor
from app.policy.allowed_actions import ActorClass, actor_classes
from app.policy.relationships import ActorContext
from app.schemas.tickets import CommentBody, TimelineEventOut
from app.services.spokes import user_ref
from app.services.workflow.common import (
    AuditEntry,
    TimelineEntry,
    Workflow,
    event_data,
    status_label,
)

TEAM_CLASSES: Final = frozenset({ActorClass.TEAM, ActorClass.ASSIGNEE})


class CommentService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._flow = Workflow(session, clock)

    def add(self, actor: Actor, ticket_no: str, body: CommentBody) -> TimelineEventOut:
        action = TicketAction.INTERNAL_NOTE if body.internal else TicketAction.COMMENT
        ticket, ctx, now = self._flow.begin(actor, ticket_no, action)
        by_team = self._is_team(ctx, ticket)
        comment = TicketEvent(
            ticket_id=ticket.id,
            at=now,
            actor_id=actor.id,
            kind=TicketEventKind.INTERNAL_NOTE if body.internal else TicketEventKind.COMMENT,
            body=body.body,
            is_public=not body.internal,
        )
        self._session.add(comment)
        ticket.updated_at = now
        if by_team:
            ticket.last_team_update_at = now
        events: list[DomainEvent] = []
        if (
            ctx.is_requester
            and not body.internal
            and ticket.status is TicketStatus.AWAITING_REQUESTER
        ):
            events.append(self._resume(ticket, actor, now))
        self._session.flush()
        events.append(
            CommentAdded(
                actor_id=actor.id,
                occurred_at=now,
                ticket_id=ticket.id,
                ticket_event_id=comment.id,
                internal=body.internal,
            )
        )
        if by_team:
            events.append(
                TeamUpdateRecorded(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id)
            )
        self._flow.publish(*events)
        author = self._session.get(User, actor.id)
        if author is None:
            raise LookupError("comment author not found")
        return TimelineEventOut(
            id=str(comment.id),
            at=comment.at,
            actor=user_ref(author),
            type=comment.kind,
            body=comment.body,
            public=comment.is_public,
        )

    @staticmethod
    def _is_team(ctx: ActorContext, ticket: Ticket) -> bool:
        return bool(actor_classes(ctx, ticket.confidential) & TEAM_CLASSES)

    def _resume(self, ticket: Ticket, actor: Actor, now: datetime) -> TicketStatusChanged:
        old_status = ticket.status
        ticket.status = TicketStatus.IN_PROGRESS
        ticket.awaiting_since = None
        self._flow.record(
            ticket,
            None,
            now,
            TimelineEntry(
                action="status_changed",
                detail=(
                    f"Status changed from {status_label(old_status)} "
                    f"to {status_label(ticket.status)} after the requester replied"
                ),
                public=True,
                data=event_data(from_status=old_status, to_status=ticket.status),
            ),
            AuditEntry(
                action="ticket_status_changed",
                old_value={"status": old_status},
                new_value={"status": ticket.status},
            ),
        )
        return TicketStatusChanged(
            actor_id=actor.id,
            occurred_at=now,
            ticket_id=ticket.id,
            from_status=old_status,
            to_status=ticket.status,
        )
