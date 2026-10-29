from collections.abc import Callable
from typing import Final

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import TicketStatus
from app.core.events import (
    EventBus,
    TeamUpdateRecorded,
    TicketAcknowledged,
    TicketCancelled,
    TicketClosed,
    TicketCreated,
    TicketDomainEvent,
    TicketEtaChanged,
    TicketPriorityChanged,
    TicketReopened,
    TicketResolved,
    TicketStatusChanged,
    TicketTransferred,
)
from app.models.sla import TimerKind
from app.models.ticket import Ticket
from app.services.policy import PolicyService
from app.services.sla.levels import apply_levels, is_running
from app.services.sla.timers import Timers

PAUSED_STATUSES: Final = frozenset({TicketStatus.AWAITING_REQUESTER, TicketStatus.ON_HOLD})
STARTED_FROM_REOPENED: Final = frozenset({TicketStatus.IN_PROGRESS, TicketStatus.ASSIGNED})

type TimerAction[E: TicketDomainEvent] = Callable[[Timers, Ticket, E], None]


def _apply[E: TicketDomainEvent](action: TimerAction[E]) -> Callable[[Session, E], None]:
    def handler(session: Session, event: E) -> None:
        ticket = session.get(Ticket, event.ticket_id)
        if ticket is None:
            return
        policy = PolicyService(session).current()
        timers = Timers(session, ticket, policy, get_settings().sla_time_scale)
        action(timers, ticket, event)
        timers.reconcile(event.occurred_at)
        session.flush()
        apply_levels(ticket, timers.all, event.occurred_at)
        session.flush()

    return handler


def on_created(timers: Timers, ticket: Ticket, _event: TicketCreated) -> None:
    timers.start_initial_response(ticket.sla_started_at)


def on_acknowledged(timers: Timers, _ticket: Ticket, event: TicketAcknowledged) -> None:
    now = event.occurred_at
    timers.mark_met(TimerKind.INITIAL_RESPONSE, now)
    timers.start_progress_update(now)
    timers.start_eta(now)


def on_team_update(timers: Timers, _ticket: Ticket, event: TeamUpdateRecorded) -> None:
    timer = timers.get(TimerKind.PROGRESS_UPDATE)
    if timer is not None and is_running(timer):
        timers.start_progress_update(event.occurred_at)


def on_status_changed(timers: Timers, _ticket: Ticket, event: TicketStatusChanged) -> None:
    now = event.occurred_at
    if event.to_status is TicketStatus.AWAITING_REQUESTER:
        timers.pause(TimerKind.PROGRESS_UPDATE, now)
        timers.pause(TimerKind.ETA, now)
        timers.start_requester_reminder(now)
        return
    if event.to_status is TicketStatus.ON_HOLD:
        timers.pause(TimerKind.PROGRESS_UPDATE, now)
        timers.pause(TimerKind.ETA, now)
        timers.start_hold_review(now)
        return
    if event.to_status is TicketStatus.IN_PROGRESS and event.from_status in PAUSED_STATUSES:
        timers.stop(TimerKind.REQUESTER_REMINDER, now)
        timers.stop(TimerKind.HOLD_REVIEW, now)
        timers.start_progress_update(now)
        timers.resume(TimerKind.ETA, now)
        return
    if event.from_status is TicketStatus.REOPENED and event.to_status in STARTED_FROM_REOPENED:
        timers.mark_met(TimerKind.INITIAL_RESPONSE, now)
        timers.start_progress_update(now)


def on_eta_changed(timers: Timers, _ticket: Ticket, event: TicketEtaChanged) -> None:
    timers.start_eta(event.occurred_at)


def on_priority_changed(timers: Timers, _ticket: Ticket, _event: TicketPriorityChanged) -> None:
    timers.recompute_initial_response_thresholds()


def on_resolved(timers: Timers, _ticket: Ticket, event: TicketResolved) -> None:
    now = event.occurred_at
    timers.mark_met(TimerKind.ETA, now)
    for kind in (TimerKind.PROGRESS_UPDATE, TimerKind.REQUESTER_REMINDER, TimerKind.HOLD_REVIEW):
        timers.stop(kind, now)
    timers.start_auto_close(now)


def on_closed(timers: Timers, _ticket: Ticket, event: TicketClosed) -> None:
    timers.stop_all(event.occurred_at)


def on_cancelled(timers: Timers, _ticket: Ticket, event: TicketCancelled) -> None:
    timers.stop_all(event.occurred_at)


def on_reopened(timers: Timers, ticket: Ticket, event: TicketReopened) -> None:
    now = event.occurred_at
    ticket.sla_started_at = now
    timers.stop(TimerKind.AUTO_CLOSE, now)
    timers.stop(TimerKind.ETA, now)
    timers.stop(TimerKind.PROGRESS_UPDATE, now)
    timers.start_initial_response(now)


def on_transferred(timers: Timers, ticket: Ticket, event: TicketTransferred) -> None:
    now = event.occurred_at
    ticket.sla_started_at = now
    for kind in (
        TimerKind.PROGRESS_UPDATE,
        TimerKind.ETA,
        TimerKind.REQUESTER_REMINDER,
        TimerKind.HOLD_REVIEW,
    ):
        timers.stop(kind, now)
    timers.start_initial_response(now)


def register_sla_handlers(target: EventBus) -> None:
    target.register(TicketCreated, _apply(on_created))
    target.register(TicketAcknowledged, _apply(on_acknowledged))
    target.register(TeamUpdateRecorded, _apply(on_team_update))
    target.register(TicketStatusChanged, _apply(on_status_changed))
    target.register(TicketEtaChanged, _apply(on_eta_changed))
    target.register(TicketPriorityChanged, _apply(on_priority_changed))
    target.register(TicketResolved, _apply(on_resolved))
    target.register(TicketClosed, _apply(on_closed))
    target.register(TicketCancelled, _apply(on_cancelled))
    target.register(TicketReopened, _apply(on_reopened))
    target.register(TicketTransferred, _apply(on_transferred))
