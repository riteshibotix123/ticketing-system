from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.enums import Priority, Role, TicketStatus
from app.core.events import TicketAcknowledged, TicketCreated, TicketStatusChanged, publish
from app.integrations.email import InMemorySender
from app.models import (
    AuditLog,
    Department,
    EscalationEvent,
    Notification,
    SlaTimer,
    Ticket,
    TicketEvent,
    TimerKind,
    User,
)
from app.services.handlers import register_all
from app.worker import JobContext
from app.worker.jobs import sla_scan
from tests.factories import (
    FACTORY_NOW,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_user,
)

T0 = FACTORY_NOW
MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class Desk:
    it: Department
    requester: User
    spoke: User
    admin: User
    super_admin: User


@pytest.fixture(autouse=True)
def handlers() -> None:
    register_all()


@pytest.fixture
def desk(db: Session) -> Desk:
    it = make_department(db, "IT")
    spoke = make_user(db, it, name="Sam Spoke")
    make_spoke_assignment(db, spoke, it)
    return Desk(
        it=it,
        requester=make_user(db, it, name="Rita Requester"),
        spoke=spoke,
        admin=make_user(db, it, role=Role.ADMIN, name="Ada Admin"),
        super_admin=make_user(db, it, role=Role.SUPER_ADMIN, name="Sue Super"),
    )


@pytest.fixture
def context(clock: FrozenClock, settings: Settings) -> JobContext:
    return JobContext(clock=clock, settings=settings, sender=InMemorySender())


def new_ticket(db: Session, desk: Desk, priority: Priority = Priority.MEDIUM) -> Ticket:
    ticket = make_ticket(db, desk.requester, desk.it, priority=priority)
    publish(db, TicketCreated(actor_id=desk.requester.id, occurred_at=T0, ticket_id=ticket.id))
    db.flush()
    return ticket


def working_ticket(db: Session, desk: Desk) -> Ticket:
    ticket = make_ticket(
        db, desk.requester, desk.it, status=TicketStatus.ACKNOWLEDGED, owner=desk.spoke
    )
    publish(db, TicketAcknowledged(actor_id=desk.spoke.id, occurred_at=T0, ticket_id=ticket.id))
    db.flush()
    return ticket


def scan_at(db: Session, clock: FrozenClock, context: JobContext, hours: float) -> int:
    clock.set(T0 + timedelta(hours=hours))
    return sla_scan.run(db, context)


def steps(db: Session, ticket: Ticket, kind: TimerKind) -> list[tuple[float, str]]:
    rows = db.scalars(
        select(EscalationEvent)
        .where(EscalationEvent.ticket_id == ticket.id, EscalationEvent.timer_kind == kind)
        .order_by(EscalationEvent.at, EscalationEvent.step_key)
    )
    return [((row.at - T0).total_seconds() / 3600, row.step_key) for row in rows]


def walk(db: Session, clock: FrozenClock, context: JobContext, thresholds: list[float]) -> None:
    for hours in thresholds:
        scan_at(db, clock, context, hours - 1 / 60)
        scan_at(db, clock, context, hours)


@pytest.mark.parametrize(
    ("priority", "expected"),
    [
        (
            Priority.LOW,
            [(18, "L1"), (24, "L2"), (48, "L3"), (72, "L3_REPEAT_1"), (96, "L3_REPEAT_2")],
        ),
        (
            Priority.MEDIUM,
            [(18, "L1"), (24, "L2"), (48, "L3"), (72, "L3_REPEAT_1"), (96, "L3_REPEAT_2")],
        ),
        (
            Priority.HIGH,
            [(18, "L1"), (24, "L2"), (36, "L3"), (60, "L3_REPEAT_1"), (84, "L3_REPEAT_2")],
        ),
        (
            Priority.CRITICAL,
            [
                (0, "CREATION_CONTACT"),
                (12, "L1"),
                (24, "L2"),
                (30, "L3"),
                (54, "L3_REPEAT_1"),
                (78, "L3_REPEAT_2"),
            ],
        ),
    ],
)
def test_initial_response_steps_per_priority(
    db: Session,
    clock: FrozenClock,
    context: JobContext,
    desk: Desk,
    priority: Priority,
    expected: list[tuple[float, str]],
) -> None:
    ticket = new_ticket(db, desk, priority)
    scan_at(db, clock, context, 0)
    walk(db, clock, context, [hours for hours, _ in expected if hours > 0])
    assert steps(db, ticket, TimerKind.INITIAL_RESPONSE) == expected


def test_progress_update_steps(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = working_ticket(db, desk)
    walk(db, clock, context, [20, 24, 48, 72])
    assert steps(db, ticket, TimerKind.PROGRESS_UPDATE) == [
        (20, "L1"),
        (24, "L2"),
        (48, "L3"),
        (72, "L3_REPEAT_1"),
    ]


def test_eta_steps(db: Session, clock: FrozenClock, context: JobContext, desk: Desk) -> None:
    ticket = working_ticket(db, desk)
    assert ticket.eta == T0 + timedelta(days=2)
    walk(db, clock, context, [46, 48, 72, 96])
    assert steps(db, ticket, TimerKind.ETA) == [
        (46, "L1"),
        (48, "L2"),
        (72, "L3"),
        (96, "L3_REPEAT_1"),
    ]


def test_levels_events_timeline_and_audit(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = new_ticket(db, desk)
    assert scan_at(db, clock, context, 18) == 1
    db.refresh(ticket)
    assert ticket.escalation_level == 1
    assert scan_at(db, clock, context, 24) == 1
    db.refresh(ticket)
    assert ticket.escalation_level == 2
    timer = db.scalars(
        select(SlaTimer).where(
            SlaTimer.ticket_id == ticket.id, SlaTimer.kind == TimerKind.INITIAL_RESPONSE
        )
    ).one()
    assert timer.level == 2
    events = db.scalars(
        select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.at)
    ).all()
    assert [(event.action, event.detail, event.is_public) for event in events] == [
        ("escalation", "L1 initial response warning", False),
        ("escalation", "L2 initial response breach", False),
    ]
    assert all(event.actor_id is None for event in events)
    audits = db.scalars(select(AuditLog.action).where(AuditLog.ticket_id == ticket.id)).all()
    assert audits == ["ticket_escalation", "ticket_escalation"]
    kinds = {
        (row.kind, row.critical)
        for row in db.scalars(
            select(Notification).where(
                Notification.ticket_id == ticket.id, Notification.kind != "ticket_created"
            )
        )
    }
    assert kinds == {("sla_warning", False), ("escalation", True)}


def test_acknowledgement_stops_escalation_and_resets_level(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = new_ticket(db, desk)
    scan_at(db, clock, context, 25)
    db.refresh(ticket)
    assert ticket.escalation_level == 2
    ticket.status = TicketStatus.ACKNOWLEDGED
    ticket.owner_id = desk.spoke.id
    ticket.eta = T0 + timedelta(days=5)
    acknowledged_at = T0 + timedelta(hours=26)
    publish(
        db,
        TicketAcknowledged(
            actor_id=desk.spoke.id, occurred_at=acknowledged_at, ticket_id=ticket.id
        ),
    )
    db.flush()
    db.refresh(ticket)
    assert ticket.escalation_level == 0
    scan_at(db, clock, context, 47)
    scan_at(db, clock, context, 49)
    assert steps(db, ticket, TimerKind.INITIAL_RESPONSE) == [(25, "L1"), (25, "L2")]


def test_outage_catch_up_emits_each_level_once(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = new_ticket(db, desk)
    assert scan_at(db, clock, context, 96) == 1
    assert [key for _, key in steps(db, ticket, TimerKind.INITIAL_RESPONSE)] == [
        "L1",
        "L2",
        "L3",
        "L3_REPEAT_2",
    ]
    timeline = db.scalars(
        select(TicketEvent.detail).where(TicketEvent.ticket_id == ticket.id)
    ).all()
    assert sorted(detail or "" for detail in timeline) == [
        "L1 initial response warning",
        "L2 initial response breach",
        "L3 initial response breach",
    ]
    escalations = db.scalars(
        select(Notification.dedupe_key).where(
            Notification.ticket_id == ticket.id,
            Notification.kind == "escalation",
            Notification.user_id == desk.super_admin.id,
        )
    ).all()
    assert [key.rsplit(":", 1)[1] for key in escalations if key] == ["L3_REPEAT_2"]
    assert scan_at(db, clock, context, 97) == 0
    assert scan_at(db, clock, context, 120) == 1
    assert steps(db, ticket, TimerKind.INITIAL_RESPONSE)[-1] == (120, "L3_REPEAT_3")


def test_pause_suspends_update_and_eta_escalation(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = working_ticket(db, desk)
    ticket.status = TicketStatus.AWAITING_REQUESTER
    publish(
        db,
        TicketStatusChanged(
            actor_id=desk.spoke.id,
            occurred_at=T0 + timedelta(hours=1),
            ticket_id=ticket.id,
            from_status=TicketStatus.ACKNOWLEDGED,
            to_status=TicketStatus.AWAITING_REQUESTER,
        ),
    )
    db.flush()
    assert scan_at(db, clock, context, 200) == 0
    assert steps(db, ticket, TimerKind.PROGRESS_UPDATE) == []
    assert steps(db, ticket, TimerKind.ETA) == []


def test_terminal_tickets_are_ignored(
    db: Session, clock: FrozenClock, context: JobContext, desk: Desk
) -> None:
    ticket = new_ticket(db, desk)
    ticket.status = TicketStatus.CANCELLED
    db.flush()
    assert scan_at(db, clock, context, 30) == 0
    assert steps(db, ticket, TimerKind.INITIAL_RESPONSE) == []


def test_repeat_interval_uses_time_scale(db: Session, clock: FrozenClock, desk: Desk) -> None:
    ticket = new_ticket(db, desk)
    settings = Settings(env=Environment.TEST, sla_time_scale=0.5)
    scaled = JobContext(clock=clock, settings=settings, sender=InMemorySender())
    scan_at(db, clock, scaled, 48 + 12)
    keys = [key for _, key in steps(db, ticket, TimerKind.INITIAL_RESPONSE)]
    assert keys == ["L1", "L2", "L3", "L3_REPEAT_1"]
