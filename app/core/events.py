import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.enums import Priority, TicketStatus
from app.models.sla import TimerKind
from app.models.ticket import CloseReason


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    actor_id: uuid.UUID | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SignupVerified(DomainEvent):
    signup_request_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class SignupDecided(DomainEvent):
    signup_request_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class UserDeactivated(DomainEvent):
    user_id: uuid.UUID
    open_ticket_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtectedActionRequested(DomainEvent):
    protected_action_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtectedActionDecided(DomainEvent):
    protected_action_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfidentialGrantChanged(DomainEvent):
    user_id: uuid.UUID
    category_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketDomainEvent(DomainEvent):
    ticket_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketCreated(TicketDomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketAcknowledged(TicketDomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketAssigned(TicketDomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketStatusChanged(TicketDomainEvent):
    from_status: TicketStatus
    to_status: TicketStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketEtaChanged(TicketDomainEvent):
    old: datetime | None
    new: datetime
    is_extension: bool
    reason: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketPriorityChanged(TicketDomainEvent):
    old: Priority
    new: Priority


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketResolved(TicketDomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketClosed(TicketDomainEvent):
    reason: CloseReason


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketReopened(TicketDomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketCancelled(TicketDomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketTransferred(TicketDomainEvent):
    from_department: str
    to_department: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamUpdateRecorded(TicketDomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class CommentAdded(TicketDomainEvent):
    ticket_event_id: uuid.UUID
    internal: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class CollaboratorChanged(TicketDomainEvent):
    user_id: uuid.UUID
    added: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SlaWarningRaised(TicketDomainEvent):
    timer_kind: TimerKind
    level: int


@dataclass(frozen=True, slots=True, kw_only=True)
class EscalationRaised(TicketDomainEvent):
    timer_kind: TimerKind
    level: int
    step_key: str


type Dispatcher = Callable[[Session, DomainEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Dispatcher]] = {}

    def register[E: DomainEvent](
        self, event_type: type[E], handler: Callable[[Session, E], None]
    ) -> None:
        def dispatch(session: Session, event: DomainEvent) -> None:
            if isinstance(event, event_type):
                handler(session, event)

        self._handlers.setdefault(event_type, []).append(dispatch)

    def publish(self, session: Session, event: DomainEvent) -> None:
        for dispatch in tuple(self._handlers.get(type(event), ())):
            dispatch(session, event)

    def handler_count(self, event_type: type[DomainEvent]) -> int:
        return len(self._handlers.get(event_type, ()))

    def clear(self) -> None:
        self._handlers.clear()


bus = EventBus()


def register[E: DomainEvent](event_type: type[E], handler: Callable[[Session, E], None]) -> None:
    bus.register(event_type, handler)


def publish(session: Session, event: DomainEvent) -> None:
    bus.publish(session, event)
