import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import AccountState, TicketAction, TicketStatus
from app.core.errors import validation_error
from app.core.events import (
    DomainEvent,
    TeamUpdateRecorded,
    TicketAcknowledged,
    TicketAssigned,
    TicketEtaChanged,
    TicketPriorityChanged,
    TicketStatusChanged,
)
from app.models.identity import User
from app.models.ticket import Ticket
from app.policy import Actor
from app.policy.relationships import ActorContext
from app.schemas.tickets import TicketOut
from app.schemas.workflow import (
    AcknowledgeBody,
    AssignBody,
    EtaBody,
    HoldBody,
    PriorityBody,
    StatusBody,
)
from app.services.spokes import department_member
from app.services.workflow.common import (
    AuditEntry,
    TimelineEntry,
    Workflow,
    event_data,
    format_time,
    status_label,
)

FUTURE: Final = "Must be in the future"
START_STATUSES: Final = frozenset(
    {TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED, TicketStatus.REOPENED}
)
RESUME_STATUSES: Final = frozenset({TicketStatus.AWAITING_REQUESTER, TicketStatus.ON_HOLD})
ASSIGN_MOVES_TO_ASSIGNED: Final = frozenset({TicketStatus.ACKNOWLEDGED, TicketStatus.REOPENED})
STATUS_TARGETS: Final = frozenset({TicketStatus.IN_PROGRESS, TicketStatus.AWAITING_REQUESTER})


class ProgressService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._flow = Workflow(session, clock)

    def acknowledge(self, actor: Actor, ticket_no: str, body: AcknowledgeBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.ACKNOWLEDGE)
        old_status = ticket.status
        if body.eta is not None:
            if body.eta <= now:
                raise validation_error({"eta": FUTURE})
            ticket.eta = body.eta
            ticket.next_checkpoint_at = None
            detail = f"Acknowledged by {actor.name}. ETA {format_time(body.eta)}"
            data = event_data(eta=body.eta)
        else:
            checkpoint = self._checkpoint(body, now)
            ticket.next_checkpoint_at = checkpoint
            detail = f"Acknowledged by {actor.name}. Next update by {format_time(checkpoint)}"
            data = event_data(no_eta_reason=body.no_eta_reason, next_checkpoint_at=checkpoint)
        ticket.owner_id = actor.id
        ticket.status = TicketStatus.ACKNOWLEDGED
        ticket.acknowledged_at = now
        ticket.last_team_update_at = now
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(action="acknowledged", detail=detail, public=True, data=data),
            AuditEntry(
                action="ticket_acknowledged",
                old_value={"status": old_status},
                new_value={
                    "status": ticket.status,
                    "owner_id": actor.id,
                    "eta": ticket.eta,
                    "next_checkpoint_at": ticket.next_checkpoint_at,
                },
            ),
        )
        self._flow.publish(
            TicketAcknowledged(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id),
            TeamUpdateRecorded(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id),
        )
        return self._flow.respond(actor, ticket)

    def assign(self, actor: Actor, ticket_no: str, body: AssignBody) -> TicketOut:
        ticket, ctx, now = self._flow.begin(actor, ticket_no, TicketAction.ASSIGN)
        assignee = self._assignee(ctx, ticket, body)
        old_status = ticket.status
        old_assignee = ticket.assignee_id
        ticket.assignee_id = assignee.id
        if old_status in ASSIGN_MOVES_TO_ASSIGNED:
            ticket.status = TicketStatus.ASSIGNED
        public_detail = f"Assigned to {assignee.name}"
        detail = f"{public_detail}. Reason: {body.reason}" if body.reason else public_detail
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(
                action="assigned",
                detail=detail,
                public_detail=public_detail,
                public=True,
                data=event_data(from_assignee_id=old_assignee, to_assignee_id=assignee.id),
            ),
            AuditEntry(
                action="ticket_assigned",
                old_value={"assignee_id": old_assignee, "status": old_status},
                new_value={"assignee_id": assignee.id, "status": ticket.status},
                reason=body.reason,
            ),
        )
        events: list[DomainEvent] = [
            TicketAssigned(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id)
        ]
        if ticket.status is not old_status:
            events.append(
                TicketStatusChanged(
                    actor_id=actor.id,
                    occurred_at=now,
                    ticket_id=ticket.id,
                    from_status=old_status,
                    to_status=ticket.status,
                )
            )
        self._flow.publish(*events)
        return self._flow.respond(actor, ticket)

    def change_status(self, actor: Actor, ticket_no: str, body: StatusBody) -> TicketOut:
        if body.status not in STATUS_TARGETS:
            raise validation_error({"status": "Choose in_progress or awaiting_requester"})
        ticket = self._flow.lock(actor, ticket_no)
        ctx = self._flow.context(actor, ticket)
        now = self._flow.clock.now()
        action = self._status_action(body.status, ticket.status)
        self._flow.authorize(action, ctx, ticket, now)
        old_status = ticket.status
        if body.status is TicketStatus.AWAITING_REQUESTER:
            if body.message is None:
                raise validation_error({"message": "Add a message for the requester"})
            ticket.awaiting_since = now
            self._flow.add_comment(ticket, actor.id, now, body.message)
        else:
            ticket.awaiting_since = None
            ticket.hold_reason = None
            ticket.hold_review_date = None
        ticket.status = body.status
        ticket.last_team_update_at = now
        self._record_status(ticket, actor, now, old_status)
        self._publish_status(ticket, actor, now, old_status)
        return self._flow.respond(actor, ticket)

    def hold(self, actor: Actor, ticket_no: str, body: HoldBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.HOLD)
        if body.review_date <= now:
            raise validation_error({"review_date": FUTURE})
        old_status = ticket.status
        ticket.status = TicketStatus.ON_HOLD
        ticket.hold_reason = body.reason
        ticket.hold_review_date = body.review_date
        ticket.last_team_update_at = now
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(
                action="hold",
                detail=(
                    f"Put on hold until {format_time(body.review_date)}. Reason: {body.reason}"
                ),
                public=True,
                data=event_data(review_date=body.review_date),
            ),
            AuditEntry(
                action="ticket_hold",
                old_value={"status": old_status},
                new_value={"status": ticket.status, "review_date": body.review_date},
                reason=body.reason,
            ),
        )
        self._publish_status(ticket, actor, now, old_status)
        return self._flow.respond(actor, ticket)

    def revise_eta(self, actor: Actor, ticket_no: str, body: EtaBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.REVISE_ETA)
        if body.eta <= now:
            raise validation_error({"eta": FUTURE})
        old_eta = ticket.eta
        if old_eta is not None and old_eta == body.eta:
            raise validation_error({"eta": "Must differ from the current ETA"})
        is_extension = old_eta is not None and body.eta > old_eta
        ticket.eta = body.eta
        ticket.last_team_update_at = now
        change = (
            f"ETA changed from {format_time(old_eta)} to {format_time(body.eta)}"
            if old_eta is not None
            else f"ETA set to {format_time(body.eta)}"
        )
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(
                action="eta_revised",
                detail=f"{change}. Reason: {body.reason}",
                public_detail=change,
                public=True,
                data=event_data(old=old_eta, new=body.eta, is_extension=is_extension),
            ),
            AuditEntry(
                action="ticket_eta_revised",
                old_value={"eta": old_eta},
                new_value={"eta": body.eta},
                reason=body.reason,
            ),
        )
        self._flow.publish(
            TicketEtaChanged(
                actor_id=actor.id,
                occurred_at=now,
                ticket_id=ticket.id,
                old=old_eta,
                new=body.eta,
                is_extension=is_extension,
                reason=body.reason,
            ),
            TeamUpdateRecorded(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id),
        )
        return self._flow.respond(actor, ticket)

    def change_priority(self, actor: Actor, ticket_no: str, body: PriorityBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.CHANGE_PRIORITY)
        old_priority = ticket.priority
        if body.priority is old_priority:
            raise validation_error({"priority": "Must differ from the current priority"})
        ticket.priority = body.priority
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(
                action="priority_changed",
                detail=(
                    f"Priority changed from {old_priority.value} to {body.priority.value}. "
                    f"Reason: {body.reason}"
                ),
                public=False,
                data=event_data(old=old_priority, new=body.priority),
            ),
            AuditEntry(
                action="ticket_priority_changed",
                old_value={"priority": old_priority},
                new_value={"priority": body.priority},
                reason=body.reason,
            ),
        )
        self._flow.publish(
            TicketPriorityChanged(
                actor_id=actor.id,
                occurred_at=now,
                ticket_id=ticket.id,
                old=old_priority,
                new=body.priority,
            )
        )
        return self._flow.respond(actor, ticket)

    @staticmethod
    def _checkpoint(body: AcknowledgeBody, now: datetime) -> datetime:
        missing = "Give an ETA, or a reason and the next checkpoint"
        fields: dict[str, str] = {}
        if body.no_eta_reason is None:
            fields["no_eta_reason"] = missing
        checkpoint = body.next_checkpoint_at
        if checkpoint is None:
            fields["next_checkpoint_at"] = missing
        elif checkpoint <= now:
            fields["next_checkpoint_at"] = FUTURE
        if fields or checkpoint is None:
            raise validation_error(fields)
        return checkpoint

    def _assignee(self, ctx: ActorContext, ticket: Ticket, body: AssignBody) -> User:
        try:
            user_id = uuid.UUID(body.assignee_id)
        except ValueError as exc:
            raise validation_error({"assignee_id": "Choose an active user"}) from exc
        if ticket.assignee_id == user_id:
            raise validation_error({"assignee_id": "This user is already the assignee"})
        user = self._session.get(User, user_id)
        if user is None or user.state is not AccountState.ACTIVE:
            raise validation_error({"assignee_id": "Choose an active user"})
        if (ctx.is_department_spoke or ctx.is_owner) and self._is_member(user, ticket):
            return user
        if ctx.is_admin or ctx.is_super_admin:
            if body.reason is None:
                raise validation_error({"reason": "A reason is required"})
            return user
        raise validation_error({"assignee_id": "Choose an active member of the department"})

    def _is_member(self, user: User, ticket: Ticket) -> bool:
        statement = select(User.id).where(
            User.id == user.id, department_member(ticket.department_id)
        )
        return self._session.scalar(statement) is not None

    @staticmethod
    def _status_action(target: TicketStatus, current: TicketStatus) -> TicketAction:
        if target is TicketStatus.AWAITING_REQUESTER:
            return TicketAction.ASK_REQUESTER
        if current in RESUME_STATUSES:
            return TicketAction.RESUME
        return TicketAction.START_WORK

    def _record_status(
        self, ticket: Ticket, actor: Actor, now: datetime, old_status: TicketStatus
    ) -> None:
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(
                action="status_changed",
                detail=(
                    f"Status changed from {status_label(old_status)} "
                    f"to {status_label(ticket.status)}"
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

    def _publish_status(
        self, ticket: Ticket, actor: Actor, now: datetime, old_status: TicketStatus
    ) -> None:
        self._flow.publish(
            TicketStatusChanged(
                actor_id=actor.id,
                occurred_at=now,
                ticket_id=ticket.id,
                from_status=old_status,
                to_status=ticket.status,
            ),
            TeamUpdateRecorded(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id),
        )
