import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy.orm import Session

from app.core.clock import Clock, to_ist
from app.core.enums import TicketAction, TicketStatus
from app.core.errors import ApiError
from app.core.events import DomainEvent, publish
from app.core.types import JsonObject
from app.models.ticket import Ticket, TicketEvent, TicketEventKind
from app.policy import Actor
from app.policy.allowed_actions import classify_denial, is_action_allowed
from app.policy.relationships import ActorContext
from app.schemas.tickets import TicketOut
from app.services.audit import AuditService, to_json_value
from app.services.policy import PolicyConfig, PolicyService
from app.services.ticket_reads import TicketPresenter, TicketReadService

TICKET_OBJECT: Final = "ticket"
TIME_FORMAT: Final = "%d %b %Y, %H:%M IST"


def format_time(value: datetime) -> str:
    return to_ist(value).strftime(TIME_FORMAT)


def status_label(status: TicketStatus) -> str:
    return status.value.replace("_", " ")


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    action: str
    detail: str
    public: bool
    public_detail: str | None = None
    data: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class AuditEntry:
    action: str
    old_value: object = None
    new_value: object = None
    reason: str | None = None


class Workflow:
    def __init__(self, session: Session, clock: Clock) -> None:
        self.session = session
        self.clock = clock
        self._reads = TicketReadService(session, clock)
        self._presenter = TicketPresenter(session, clock)
        self._audit = AuditService(session, clock)

    def policy(self) -> PolicyConfig:
        return PolicyService(self.session).current()

    def lock(self, actor: Actor, ticket_no: str) -> Ticket:
        return self._reads.load_visible(actor, ticket_no, for_update=True)

    def context(self, actor: Actor, ticket: Ticket) -> ActorContext:
        return self._presenter.context(actor, ticket)

    def is_allowed(
        self, action: TicketAction, ctx: ActorContext, ticket: Ticket, now: datetime
    ) -> bool:
        return is_action_allowed(action, ctx, ticket, self.policy(), now)

    @staticmethod
    def denial(action: TicketAction, ctx: ActorContext, ticket: Ticket) -> ApiError:
        return ApiError(classify_denial(action, ctx, ticket))

    def authorize(
        self, action: TicketAction, ctx: ActorContext, ticket: Ticket, now: datetime
    ) -> None:
        if not self.is_allowed(action, ctx, ticket, now):
            raise self.denial(action, ctx, ticket)

    def begin(
        self, actor: Actor, ticket_no: str, action: TicketAction
    ) -> tuple[Ticket, ActorContext, datetime]:
        ticket = self.lock(actor, ticket_no)
        ctx = self.context(actor, ticket)
        now = self.clock.now()
        self.authorize(action, ctx, ticket, now)
        return ticket, ctx, now

    def record(
        self,
        ticket: Ticket,
        actor_id: uuid.UUID | None,
        now: datetime,
        timeline: TimelineEntry,
        audit: AuditEntry,
    ) -> TicketEvent:
        event = TicketEvent(
            ticket_id=ticket.id,
            at=now,
            actor_id=actor_id,
            kind=TicketEventKind.AUDIT,
            action=timeline.action,
            detail=timeline.detail,
            public_detail=timeline.public_detail,
            is_public=timeline.public,
            data=timeline.data,
        )
        self.session.add(event)
        ticket.updated_at = now
        self._audit.record(
            action=audit.action,
            object_type=TICKET_OBJECT,
            object_id=ticket.ticket_no,
            actor_id=actor_id,
            old_value=audit.old_value,
            new_value=audit.new_value,
            reason=audit.reason,
            ticket_id=ticket.id,
            department_id=ticket.department_id,
            is_confidential_ticket=ticket.confidential,
        )
        return event

    def add_comment(
        self, ticket: Ticket, actor_id: uuid.UUID, now: datetime, body: str
    ) -> TicketEvent:
        event = TicketEvent(
            ticket_id=ticket.id,
            at=now,
            actor_id=actor_id,
            kind=TicketEventKind.COMMENT,
            body=body,
            is_public=True,
        )
        self.session.add(event)
        return event

    def publish(self, *events: DomainEvent) -> None:
        self.session.flush()
        for event in events:
            publish(self.session, event)

    def respond(self, actor: Actor, ticket: Ticket) -> TicketOut:
        self.session.flush()
        return self._presenter.present_one(actor, ticket)


def event_data(**values: object) -> JsonObject:
    data = to_json_value(values)
    if not isinstance(data, dict):
        raise TypeError("event data must be an object")
    return data
