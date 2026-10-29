import uuid
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import TicketAction, TicketStatus
from app.core.errors import ApiError, ErrorCode
from app.core.events import (
    TicketCancelled,
    TicketClosed,
    TicketReopened,
    TicketResolved,
)
from app.core.types import JsonObject
from app.models.ticket import CloseReason, Ticket
from app.policy import Actor
from app.policy.allowed_actions import REOPENABLE_STATUSES
from app.schemas.tickets import TicketOut
from app.schemas.workflow import ConfirmClosureBody, ReasonBody, ResolveBody
from app.services.policy import PolicyConfig
from app.services.workflow.common import AuditEntry, TimelineEntry, Workflow, event_data

CONFIRMED_DETAIL: Final = "Closure confirmed by the requester"


def reopen_denied(ticket: Ticket, policy: PolicyConfig) -> ApiError:
    if ticket.reopen_count >= policy.max_reopens:
        message = "This ticket has been reopened the maximum number of times"
    else:
        message = "The reopen window has passed"
    window_ends = (
        ticket.resolved_at + timedelta(days=policy.reopen_window_days)
        if ticket.resolved_at is not None
        else None
    )
    details = event_data(
        reopen_count=ticket.reopen_count,
        max_reopens=policy.max_reopens,
        reopen_window_days=policy.reopen_window_days,
        reopen_window_ends_at=window_ends,
    )
    return ApiError(ErrorCode.INVALID_TRANSITION, message, details=details)


class ClosureService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._flow = Workflow(session, clock)

    def resolve(self, actor: Actor, ticket_no: str, body: ResolveBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.RESOLVE)
        old_status = ticket.status
        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = now
        ticket.resolution_summary = body.summary
        ticket.last_team_update_at = now
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(action="resolved", detail=f"Resolved: {body.summary}", public=True),
            AuditEntry(
                action="ticket_resolved",
                old_value={"status": old_status},
                new_value={"status": ticket.status, "resolution_summary": body.summary},
            ),
        )
        self._flow.publish(TicketResolved(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id))
        return self._flow.respond(actor, ticket)

    def confirm_closure(self, actor: Actor, ticket_no: str, body: ConfirmClosureBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.CONFIRM_CLOSURE)
        comment = body.comment or None
        ticket.feedback_rating = body.rating
        ticket.feedback_comment = comment
        self._close(
            ticket,
            actor,
            now,
            CloseReason.CONFIRMED,
            CONFIRMED_DETAIL,
            reason=None,
            feedback=event_data(rating=body.rating, comment=comment),
        )
        return self._flow.respond(actor, ticket)

    def close(self, actor: Actor, ticket_no: str, body: ReasonBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.CLOSE_ADMIN)
        detail = f"Closed by {actor.name}. Reason: {body.reason}"
        self._close(ticket, actor, now, CloseReason.ADMIN, detail, reason=body.reason)
        return self._flow.respond(actor, ticket)

    def reopen(self, actor: Actor, ticket_no: str, body: ReasonBody) -> TicketOut:
        ticket = self._flow.lock(actor, ticket_no)
        ctx = self._flow.context(actor, ticket)
        now = self._flow.clock.now()
        if not self._flow.is_allowed(TicketAction.REOPEN, ctx, ticket, now):
            denial = self._flow.denial(TicketAction.REOPEN, ctx, ticket)
            if denial.code is ErrorCode.INVALID_TRANSITION and ticket.status in REOPENABLE_STATUSES:
                raise reopen_denied(ticket, self._flow.policy())
            raise denial
        old_status = ticket.status
        old_resolution = ticket.resolution_summary
        ticket.status = TicketStatus.REOPENED
        ticket.reopen_count += 1
        ticket.resolved_at = None
        ticket.closed_at = None
        ticket.resolution_summary = None
        ticket.last_team_update_at = None
        ticket.eta = None
        ticket.next_checkpoint_at = None
        ticket.sla_started_at = now
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(
                action="reopened",
                detail=f"Reopened. Reason: {body.reason}",
                public=True,
                data=event_data(previous_resolution=old_resolution),
            ),
            AuditEntry(
                action="ticket_reopened",
                old_value={"status": old_status, "resolution_summary": old_resolution},
                new_value={"status": ticket.status, "reopen_count": ticket.reopen_count},
                reason=body.reason,
            ),
        )
        self._flow.publish(TicketReopened(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id))
        return self._flow.respond(actor, ticket)

    def cancel(self, actor: Actor, ticket_no: str, body: ReasonBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.CANCEL)
        old_status = ticket.status
        ticket.status = TicketStatus.CANCELLED
        ticket.cancel_reason = body.reason
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(
                action="cancelled", detail=f"Cancelled. Reason: {body.reason}", public=True
            ),
            AuditEntry(
                action="ticket_cancelled",
                old_value={"status": old_status},
                new_value={"status": ticket.status},
                reason=body.reason,
            ),
        )
        self._flow.publish(TicketCancelled(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id))
        return self._flow.respond(actor, ticket)

    def _close(
        self,
        ticket: Ticket,
        actor: Actor,
        now: datetime,
        close_reason: CloseReason,
        detail: str,
        *,
        reason: str | None,
        feedback: JsonObject | None = None,
    ) -> None:
        close_ticket(self._flow, ticket, actor.id, now, close_reason, detail, reason, feedback)


def close_ticket(
    flow: Workflow,
    ticket: Ticket,
    actor_id: uuid.UUID | None,
    now: datetime,
    close_reason: CloseReason,
    detail: str,
    reason: str | None = None,
    feedback: JsonObject | None = None,
) -> None:
    old_status = ticket.status
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = now
    ticket.close_reason = close_reason
    flow.record(
        ticket,
        actor_id,
        now,
        TimelineEntry(
            action="closed",
            detail=detail,
            public=True,
            data=event_data(close_reason=close_reason, feedback=feedback),
        ),
        AuditEntry(
            action="ticket_closed",
            old_value={"status": old_status},
            new_value={"status": ticket.status, "close_reason": close_reason, "feedback": feedback},
            reason=reason,
        ),
    )
    flow.publish(
        TicketClosed(actor_id=actor_id, occurred_at=now, ticket_id=ticket.id, reason=close_reason)
    )
