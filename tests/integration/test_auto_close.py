from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.enums import TicketStatus
from app.core.events import TicketResolved, publish
from app.core.types import JsonObject
from app.integrations.email import InMemorySender
from app.models import CloseReason, Notification, SlaTimer, Ticket, TicketEvent, TimerKind
from app.services.handlers import register_all
from app.worker import JobContext
from app.worker.jobs import auto_close
from tests.factories import make_department, make_policy_version, make_ticket, make_user

FRIDAY = datetime(2026, 10, 30, 4, 30, tzinfo=UTC)
WEDNESDAY = datetime(2026, 11, 4, 4, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def handlers() -> None:
    register_all()


@pytest.fixture
def context(clock: FrozenClock, settings: Settings) -> JobContext:
    return JobContext(clock=clock, settings=settings, sender=InMemorySender())


def resolved_ticket(db: Session) -> Ticket:
    it = make_department(db, "IT")
    ticket = make_ticket(db, make_user(db, it), it, status=TicketStatus.RESOLVED)
    ticket.resolved_at = FRIDAY
    publish(db, TicketResolved(actor_id=ticket.owner_id, occurred_at=FRIDAY, ticket_id=ticket.id))
    db.flush()
    return ticket


def status_of(db: Session, ticket: Ticket) -> TicketStatus:
    db.refresh(ticket)
    return ticket.status


def auto_close_timer(db: Session, ticket: Ticket) -> SlaTimer | None:
    return db.scalars(
        select(SlaTimer).where(
            SlaTimer.ticket_id == ticket.id, SlaTimer.kind == TimerKind.AUTO_CLOSE
        )
    ).first()


def test_closes_after_three_business_days_across_weekend(
    db: Session, clock: FrozenClock, context: JobContext
) -> None:
    ticket = resolved_ticket(db)
    timer = auto_close_timer(db, ticket)
    assert timer is not None
    assert timer.due_at == WEDNESDAY
    clock.set(WEDNESDAY - timedelta(minutes=1))
    assert auto_close.run(db, context) == 0
    assert status_of(db, ticket) is TicketStatus.RESOLVED
    clock.set(WEDNESDAY)
    assert auto_close.run(db, context) == 1
    assert status_of(db, ticket) is TicketStatus.CLOSED
    assert ticket.close_reason is CloseReason.AUTO
    assert ticket.closed_at == WEDNESDAY
    closed = db.scalars(
        select(TicketEvent).where(
            TicketEvent.ticket_id == ticket.id, TicketEvent.action == "closed"
        )
    ).one()
    assert closed.actor_id is None
    db.refresh(timer)
    assert timer.stopped_at == WEDNESDAY
    kinds = db.scalars(select(Notification.kind).where(Notification.ticket_id == ticket.id)).all()
    assert "closed" in kinds
    assert auto_close.run(db, context) == 0


def test_reopened_ticket_is_not_closed(
    db: Session, clock: FrozenClock, context: JobContext
) -> None:
    ticket = resolved_ticket(db)
    ticket.status = TicketStatus.REOPENED
    db.flush()
    clock.set(WEDNESDAY + timedelta(days=1))
    assert auto_close.run(db, context) == 0
    assert status_of(db, ticket) is TicketStatus.REOPENED


def test_disabled_auto_close_starts_no_timer(db: Session) -> None:
    config: JsonObject = {
        "initial_response_hours": 24,
        "warning_hours": {"low": 18, "medium": 18, "high": 18, "critical": 12},
        "l3_hours": {"low": 48, "medium": 48, "high": 36, "critical": 30},
        "update_warning_hours": 20,
        "update_cadence_hours": 24,
        "eta_warning_hours": 2,
        "escalation_repeat_hours": 24,
        "requester_reminder_hours": 48,
        "auto_close_business_days": None,
        "reopen_window_days": 7,
        "max_reopens": 3,
        "sla_mode": "calendar",
        "admins_can_manage_departments": True,
    }
    make_policy_version(db, 2, config)
    ticket = resolved_ticket(db)
    assert auto_close_timer(db, ticket) is None
