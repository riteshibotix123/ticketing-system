from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import get_settings
from app.core.enums import Priority, TicketStatus
from app.core.events import (
    DomainEvent,
    EventBus,
    TeamUpdateRecorded,
    TicketAcknowledged,
    TicketCancelled,
    TicketClosed,
    TicketCreated,
    TicketEtaChanged,
    TicketPriorityChanged,
    TicketReopened,
    TicketResolved,
    TicketStatusChanged,
    TicketTransferred,
)
from app.models import CloseReason, SlaTimer, Ticket, TimerKind
from app.services.handlers import register_all
from app.services.policy import PolicyService
from app.services.sla.due_time import add_business_days
from app.services.sla.levels import recompute_ticket
from app.services.sla.timers import Timers
from tests.factories import FACTORY_NOW, make_department, make_ticket, make_user

T0 = FACTORY_NOW
H = timedelta(hours=1)


@pytest.fixture
def bus() -> EventBus:
    target = EventBus()
    register_all(target)
    return target


@pytest.fixture
def ticket(db: Session) -> Ticket:
    it = make_department(db, "IT")
    return make_ticket(db, make_user(db, it), it)


def timers_of(db: Session, ticket: Ticket) -> dict[TimerKind, SlaTimer]:
    db.flush()
    rows = db.scalars(select(SlaTimer).where(SlaTimer.ticket_id == ticket.id))
    return {timer.kind: timer for timer in rows}


def snapshot(db: Session, ticket: Ticket) -> dict[TimerKind, tuple[object, ...]]:
    return {
        kind: (
            timer.cycle,
            timer.started_at,
            timer.warning_at,
            timer.due_at,
            timer.l3_at,
            timer.paused_at,
            timer.paused_seconds,
            timer.met_at,
            timer.stopped_at,
            timer.level,
        )
        for kind, timer in timers_of(db, ticket).items()
    }


def emit(db: Session, bus: EventBus, event: DomainEvent) -> None:
    bus.publish(db, event)


def create(db: Session, bus: EventBus, ticket: Ticket) -> None:
    emit(
        db,
        bus,
        TicketCreated(actor_id=None, occurred_at=ticket.sla_started_at, ticket_id=ticket.id),
    )


def acknowledge(
    db: Session,
    bus: EventBus,
    ticket: Ticket,
    at: datetime,
    *,
    eta: datetime | None = None,
    checkpoint: datetime | None = None,
) -> None:
    ticket.status = TicketStatus.ACKNOWLEDGED
    ticket.acknowledged_at = at
    ticket.eta = eta
    ticket.next_checkpoint_at = checkpoint
    emit(db, bus, TicketAcknowledged(actor_id=None, occurred_at=at, ticket_id=ticket.id))


def change_status(
    db: Session, bus: EventBus, ticket: Ticket, to_status: TicketStatus, at: datetime
) -> None:
    from_status = ticket.status
    ticket.status = to_status
    emit(
        db,
        bus,
        TicketStatusChanged(
            actor_id=None,
            occurred_at=at,
            ticket_id=ticket.id,
            from_status=from_status,
            to_status=to_status,
        ),
    )


def working(db: Session, bus: EventBus, ticket: Ticket) -> None:
    create(db, bus, ticket)
    acknowledge(db, bus, ticket, T0 + H, eta=T0 + 48 * H)
    change_status(db, bus, ticket, TicketStatus.IN_PROGRESS, T0 + 2 * H)


@pytest.mark.parametrize(
    ("priority", "warning", "l3"),
    [
        (Priority.LOW, 18, 48),
        (Priority.MEDIUM, 18, 48),
        (Priority.HIGH, 18, 36),
        (Priority.CRITICAL, 12, 30),
    ],
)
def test_created_starts_initial_response_per_priority(
    db: Session, bus: EventBus, ticket: Ticket, priority: Priority, warning: int, l3: int
) -> None:
    ticket.priority = priority
    create(db, bus, ticket)
    timer = timers_of(db, ticket)[TimerKind.INITIAL_RESPONSE]
    assert timer.cycle == 1
    assert timer.started_at == T0
    assert timer.warning_at == T0 + warning * H
    assert timer.due_at == T0 + 24 * H
    assert timer.l3_at == T0 + l3 * H
    for hours, level in [(0, 0), (warning - 0.01, 0), (warning, 1), (24, 2), (l3, 3)]:
        recompute_ticket(db, FrozenClock(T0 + hours * H), ticket)
        assert timer.level == level
        assert ticket.escalation_level == level


def test_sla_time_scale_shortens_durations(
    db: Session, bus: EventBus, ticket: Ticket, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SLA_TIME_SCALE", "0.5")
    get_settings.cache_clear()
    create(db, bus, ticket)
    timer = timers_of(db, ticket)[TimerKind.INITIAL_RESPONSE]
    assert timer.warning_at == T0 + 9 * H
    assert timer.due_at == T0 + 12 * H
    assert timer.l3_at == T0 + 24 * H


def test_acknowledged_meets_initial_response_and_starts_update_and_eta(
    db: Session, bus: EventBus, ticket: Ticket
) -> None:
    create(db, bus, ticket)
    acknowledge(db, bus, ticket, T0 + H, eta=T0 + 30 * H)
    timers = timers_of(db, ticket)
    assert timers[TimerKind.INITIAL_RESPONSE].met_at == T0 + H
    progress = timers[TimerKind.PROGRESS_UPDATE]
    assert (progress.warning_at, progress.due_at, progress.l3_at) == (
        T0 + 21 * H,
        T0 + 25 * H,
        T0 + 49 * H,
    )
    eta = timers[TimerKind.ETA]
    assert (eta.warning_at, eta.due_at, eta.l3_at) == (T0 + 28 * H, T0 + 30 * H, T0 + 54 * H)
    recompute_ticket(db, FrozenClock(T0 + 22 * H), ticket)
    assert ticket.update_overdue is True
    assert ticket.escalation_level == 1


def test_acknowledged_without_eta_uses_checkpoint(
    db: Session, bus: EventBus, ticket: Ticket
) -> None:
    create(db, bus, ticket)
    acknowledge(db, bus, ticket, T0 + H, checkpoint=T0 + 10 * H)
    assert timers_of(db, ticket)[TimerKind.ETA].due_at == T0 + 10 * H


def test_team_update_restarts_progress_update(db: Session, bus: EventBus, ticket: Ticket) -> None:
    working(db, bus, ticket)
    before = timers_of(db, ticket)[TimerKind.PROGRESS_UPDATE].cycle
    emit(db, bus, TeamUpdateRecorded(actor_id=None, occurred_at=T0 + 10 * H, ticket_id=ticket.id))
    progress = timers_of(db, ticket)[TimerKind.PROGRESS_UPDATE]
    assert progress.cycle == before + 1
    assert progress.started_at == T0 + 10 * H
    assert progress.due_at == T0 + 34 * H
    assert progress.level == 0


def test_team_update_ignored_when_paused_or_not_started(
    db: Session, bus: EventBus, ticket: Ticket
) -> None:
    create(db, bus, ticket)
    emit(db, bus, TeamUpdateRecorded(actor_id=None, occurred_at=T0 + H, ticket_id=ticket.id))
    assert TimerKind.PROGRESS_UPDATE not in timers_of(db, ticket)
    acknowledge(db, bus, ticket, T0 + H, eta=T0 + 48 * H)
    change_status(db, bus, ticket, TicketStatus.IN_PROGRESS, T0 + 2 * H)
    change_status(db, bus, ticket, TicketStatus.AWAITING_REQUESTER, T0 + 3 * H)
    before = snapshot(db, ticket)[TimerKind.PROGRESS_UPDATE]
    emit(db, bus, TeamUpdateRecorded(actor_id=None, occurred_at=T0 + 4 * H, ticket_id=ticket.id))
    assert snapshot(db, ticket)[TimerKind.PROGRESS_UPDATE] == before


def test_awaiting_requester_pauses_and_resume_restarts(
    db: Session, bus: EventBus, ticket: Ticket
) -> None:
    working(db, bus, ticket)
    change_status(db, bus, ticket, TicketStatus.AWAITING_REQUESTER, T0 + 5 * H)
    timers = timers_of(db, ticket)
    assert timers[TimerKind.PROGRESS_UPDATE].paused_at == T0 + 5 * H
    assert timers[TimerKind.ETA].paused_at == T0 + 5 * H
    reminder = timers[TimerKind.REQUESTER_REMINDER]
    assert reminder.due_at == T0 + 53 * H
    recompute_ticket(db, FrozenClock(T0 + 100 * H), ticket)
    assert ticket.escalation_level == 0
    progress_cycle = timers[TimerKind.PROGRESS_UPDATE].cycle
    change_status(db, bus, ticket, TicketStatus.IN_PROGRESS, T0 + 8 * H)
    timers = timers_of(db, ticket)
    assert timers[TimerKind.REQUESTER_REMINDER].stopped_at == T0 + 8 * H
    progress = timers[TimerKind.PROGRESS_UPDATE]
    assert progress.cycle == progress_cycle + 1
    assert progress.paused_at is None
    assert progress.due_at == T0 + 32 * H
    eta = timers[TimerKind.ETA]
    assert eta.paused_at is None
    assert eta.paused_seconds == 3 * 3600
    assert eta.due_at == T0 + 48 * H


def test_on_hold_starts_hold_review(db: Session, bus: EventBus, ticket: Ticket) -> None:
    working(db, bus, ticket)
    ticket.hold_review_date = T0 + 72 * H
    change_status(db, bus, ticket, TicketStatus.ON_HOLD, T0 + 5 * H)
    timers = timers_of(db, ticket)
    assert timers[TimerKind.HOLD_REVIEW].due_at == T0 + 72 * H
    assert timers[TimerKind.PROGRESS_UPDATE].paused_at == T0 + 5 * H
    change_status(db, bus, ticket, TicketStatus.IN_PROGRESS, T0 + 6 * H)
    timers = timers_of(db, ticket)
    assert timers[TimerKind.HOLD_REVIEW].stopped_at == T0 + 6 * H
    assert timers[TimerKind.ETA].paused_seconds == 3600


def test_eta_change_restarts_eta(db: Session, bus: EventBus, ticket: Ticket) -> None:
    working(db, bus, ticket)
    cycle = timers_of(db, ticket)[TimerKind.ETA].cycle
    ticket.eta = T0 + 96 * H
    emit(
        db,
        bus,
        TicketEtaChanged(
            actor_id=None,
            occurred_at=T0 + 10 * H,
            ticket_id=ticket.id,
            old=T0 + 48 * H,
            new=T0 + 96 * H,
            is_extension=True,
            reason="Vendor delay",
        ),
    )
    eta = timers_of(db, ticket)[TimerKind.ETA]
    assert eta.cycle == cycle + 1
    assert (eta.warning_at, eta.due_at, eta.l3_at) == (T0 + 94 * H, T0 + 96 * H, T0 + 120 * H)


def test_priority_change_recomputes_unmet_initial_response(
    db: Session, bus: EventBus, ticket: Ticket
) -> None:
    create(db, bus, ticket)
    ticket.priority = Priority.CRITICAL
    emit(
        db,
        bus,
        TicketPriorityChanged(
            actor_id=None,
            occurred_at=T0 + 13 * H,
            ticket_id=ticket.id,
            old=Priority.MEDIUM,
            new=Priority.CRITICAL,
        ),
    )
    timer = timers_of(db, ticket)[TimerKind.INITIAL_RESPONSE]
    assert (timer.warning_at, timer.due_at, timer.l3_at) == (T0 + 12 * H, T0 + 24 * H, T0 + 30 * H)
    assert timer.level == 1
    assert ticket.escalation_level == 1


def test_priority_change_leaves_met_initial_response(
    db: Session, bus: EventBus, ticket: Ticket
) -> None:
    working(db, bus, ticket)
    before = snapshot(db, ticket)[TimerKind.INITIAL_RESPONSE]
    ticket.priority = Priority.CRITICAL
    emit(
        db,
        bus,
        TicketPriorityChanged(
            actor_id=None,
            occurred_at=T0 + 3 * H,
            ticket_id=ticket.id,
            old=Priority.MEDIUM,
            new=Priority.CRITICAL,
        ),
    )
    assert snapshot(db, ticket)[TimerKind.INITIAL_RESPONSE] == before


def resolve(db: Session, bus: EventBus, ticket: Ticket, at: datetime) -> None:
    ticket.status = TicketStatus.RESOLVED
    ticket.resolved_at = at
    emit(db, bus, TicketResolved(actor_id=None, occurred_at=at, ticket_id=ticket.id))


def test_resolved_marks_eta_and_starts_auto_close(
    db: Session, bus: EventBus, ticket: Ticket
) -> None:
    working(db, bus, ticket)
    resolve(db, bus, ticket, T0 + 50 * H)
    timers = timers_of(db, ticket)
    assert timers[TimerKind.ETA].met_at == T0 + 50 * H
    assert timers[TimerKind.PROGRESS_UPDATE].stopped_at == T0 + 50 * H
    assert timers[TimerKind.AUTO_CLOSE].due_at == add_business_days(T0 + 50 * H, 3)
    assert ticket.escalation_level == 0


def test_resolved_without_auto_close_policy(db: Session, bus: EventBus, ticket: Ticket) -> None:
    version = PolicyService(db).current_version()
    version.config = {**version.config, "auto_close_business_days": None}
    db.flush()
    working(db, bus, ticket)
    resolve(db, bus, ticket, T0 + 5 * H)
    assert TimerKind.AUTO_CLOSE not in timers_of(db, ticket)


@pytest.mark.parametrize("terminal", [TicketStatus.CLOSED, TicketStatus.CANCELLED])
def test_closed_and_cancelled_stop_every_timer(
    db: Session, bus: EventBus, ticket: Ticket, terminal: TicketStatus
) -> None:
    working(db, bus, ticket)
    ticket.status = terminal
    event: DomainEvent = (
        TicketClosed(
            actor_id=None, occurred_at=T0 + 9 * H, ticket_id=ticket.id, reason=CloseReason.ADMIN
        )
        if terminal is TicketStatus.CLOSED
        else TicketCancelled(actor_id=None, occurred_at=T0 + 9 * H, ticket_id=ticket.id)
    )
    emit(db, bus, event)
    for timer in timers_of(db, ticket).values():
        assert timer.met_at is not None or timer.stopped_at is not None
        assert timer.level == 0
    assert ticket.escalation_level == 0


def test_reopen_starts_new_initial_response_cycle(
    db: Session, bus: EventBus, ticket: Ticket
) -> None:
    working(db, bus, ticket)
    resolve(db, bus, ticket, T0 + 10 * H)
    ticket.status = TicketStatus.REOPENED
    ticket.reopen_count = 1
    emit(db, bus, TicketReopened(actor_id=None, occurred_at=T0 + 20 * H, ticket_id=ticket.id))
    timers = timers_of(db, ticket)
    initial = timers[TimerKind.INITIAL_RESPONSE]
    assert initial.cycle == 2
    assert initial.met_at is None
    assert initial.due_at == T0 + 44 * H
    assert ticket.sla_started_at == T0 + 20 * H
    assert timers[TimerKind.AUTO_CLOSE].stopped_at == T0 + 20 * H
    assert timers[TimerKind.ETA].met_at is not None
    assert timers[TimerKind.PROGRESS_UPDATE].stopped_at is not None
    change_status(db, bus, ticket, TicketStatus.IN_PROGRESS, T0 + 21 * H)
    timers = timers_of(db, ticket)
    assert timers[TimerKind.INITIAL_RESPONSE].met_at == T0 + 21 * H
    progress = timers[TimerKind.PROGRESS_UPDATE]
    assert progress.stopped_at is None
    assert progress.started_at == T0 + 21 * H


def test_transfer_restarts_initial_response(db: Session, bus: EventBus, ticket: Ticket) -> None:
    working(db, bus, ticket)
    ticket.status = TicketStatus.NEW
    emit(
        db,
        bus,
        TicketTransferred(
            actor_id=None,
            occurred_at=T0 + 6 * H,
            ticket_id=ticket.id,
            from_department="IT",
            to_department="HR",
        ),
    )
    timers = timers_of(db, ticket)
    initial = timers[TimerKind.INITIAL_RESPONSE]
    assert initial.cycle == 2
    assert initial.started_at == T0 + 6 * H
    assert initial.met_at is None
    assert ticket.sla_started_at == T0 + 6 * H
    for kind in (TimerKind.PROGRESS_UPDATE, TimerKind.ETA):
        assert timers[kind].stopped_at == T0 + 6 * H


@pytest.mark.parametrize("status", list(TicketStatus))
def test_reconcile_is_idempotent(db: Session, ticket: Ticket, status: TicketStatus) -> None:
    ticket.status = status
    ticket.acknowledged_at = T0 + H
    ticket.eta = T0 + 48 * H
    ticket.resolved_at = T0 + 5 * H
    ticket.awaiting_since = T0 + 2 * H
    ticket.hold_review_date = T0 + 72 * H
    policy = PolicyService(db).current()
    Timers(db, ticket, policy, 1.0).reconcile(T0 + 6 * H)
    first = snapshot(db, ticket)
    Timers(db, ticket, policy, 1.0).reconcile(T0 + 7 * H)
    assert snapshot(db, ticket) == first
    active = {
        kind
        for kind, timer in timers_of(db, ticket).items()
        if timer.met_at is None and timer.stopped_at is None
    }
    expected = {
        TicketStatus.NEW: {TimerKind.INITIAL_RESPONSE},
        TicketStatus.REOPENED: {TimerKind.INITIAL_RESPONSE},
        TicketStatus.ACKNOWLEDGED: {TimerKind.PROGRESS_UPDATE, TimerKind.ETA},
        TicketStatus.ASSIGNED: {TimerKind.PROGRESS_UPDATE, TimerKind.ETA},
        TicketStatus.IN_PROGRESS: {TimerKind.PROGRESS_UPDATE, TimerKind.ETA},
        TicketStatus.AWAITING_REQUESTER: {
            TimerKind.PROGRESS_UPDATE,
            TimerKind.ETA,
            TimerKind.REQUESTER_REMINDER,
        },
        TicketStatus.ON_HOLD: {TimerKind.PROGRESS_UPDATE, TimerKind.ETA, TimerKind.HOLD_REVIEW},
        TicketStatus.RESOLVED: {TimerKind.AUTO_CLOSE},
        TicketStatus.CLOSED: set(),
        TicketStatus.CANCELLED: set(),
    }
    assert active == expected[status]


def test_handlers_ignore_unknown_ticket(db: Session, bus: EventBus, ticket: Ticket) -> None:
    other = TicketCreated(actor_id=None, occurred_at=T0, ticket_id=ticket.requester_id)
    emit(db, bus, other)
    assert timers_of(db, ticket) == {}
