from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import TicketStatus
from app.models import (
    CloseReason,
    Department,
    Ticket,
    TicketEventKind,
    TimerKind,
    User,
)
from tests.factories import (
    FACTORY_NOW,
    make_attachment,
    make_category,
    make_collaborator,
    make_department,
    make_escalation_event,
    make_notification,
    make_outbox_email,
    make_ticket,
    make_ticket_counter,
    make_ticket_event,
    make_timer,
    make_user,
)


def _in_savepoint(db: Session, action: Callable[[], object]) -> None:
    with db.begin_nested():
        action()
        db.flush()


def _violates(
    db: Session,
    action: Callable[[], object],
    expected: type[DBAPIError] = IntegrityError,
) -> None:
    with pytest.raises(expected):
        _in_savepoint(db, action)


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT")


@pytest.fixture
def requester(db: Session, it: Department) -> User:
    return make_user(db, it)


@pytest.fixture
def ticket(db: Session, it: Department, requester: User) -> Ticket:
    return make_ticket(db, requester, it)


@pytest.mark.parametrize("status", list(TicketStatus))
def test_factory_builds_ticket_in_every_status(
    db: Session, it: Department, requester: User, status: TicketStatus
) -> None:
    ticket = make_ticket(db, requester, it, status=status)
    stored = db.execute(
        text("SELECT status, escalation_level, update_overdue FROM tickets WHERE id = :id"),
        {"id": ticket.id},
    ).one()
    assert tuple(stored) == (status.value, 0, False)
    has_owner = status not in {TicketStatus.NEW, TicketStatus.CANCELLED}
    assert (ticket.owner_id is not None) is has_owner
    assert (ticket.acknowledged_at is not None) is has_owner
    if status is TicketStatus.CLOSED:
        assert ticket.close_reason is CloseReason.CONFIRMED
    if status is TicketStatus.ON_HOLD:
        assert ticket.hold_reason is not None
    if status is TicketStatus.REOPENED:
        assert ticket.reopen_count == 1


def test_ticket_number_unique(db: Session, it: Department, requester: User) -> None:
    make_ticket(db, requester, it, ticket_no="IBX-IT-2026-000001")
    _violates(db, lambda: make_ticket(db, requester, it, ticket_no="IBX-IT-2026-000001"))


@pytest.mark.parametrize(
    "ticket_no", ["IBX-it-2026-000001", "IBX-IT-26-000001", "IBX-IT-2026-1", "TKT-IT-2026-000001"]
)
def test_ticket_number_format(db: Session, it: Department, requester: User, ticket_no: str) -> None:
    _violates(db, lambda: make_ticket(db, requester, it, ticket_no=ticket_no))


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_feedback_rating_out_of_range(db: Session, ticket: Ticket, rating: int) -> None:
    def rate() -> None:
        ticket.feedback_rating = rating

    _violates(db, rate)


@pytest.mark.parametrize("rating", [1, 3, 5])
def test_feedback_rating_in_range(db: Session, ticket: Ticket, rating: int) -> None:
    ticket.feedback_rating = rating
    db.flush()
    assert ticket.feedback_rating == rating


@pytest.mark.parametrize("level", [-1, 4])
def test_escalation_level_range(db: Session, ticket: Ticket, level: int) -> None:
    def escalate() -> None:
        ticket.escalation_level = level

    _violates(db, escalate)


def test_ticket_counter_primary_key(db: Session) -> None:
    make_ticket_counter(db, "IT", 2026)
    make_ticket_counter(db, "IT", 2027)
    make_ticket_counter(db, "HR", 2026)
    _violates(db, lambda: make_ticket_counter(db, "IT", 2026))


def test_one_timer_per_kind(db: Session, ticket: Ticket) -> None:
    make_timer(db, ticket, TimerKind.INITIAL_RESPONSE)
    make_timer(db, ticket, TimerKind.PROGRESS_UPDATE)
    make_timer(db, ticket, TimerKind.AUTO_CLOSE)
    _violates(db, lambda: make_timer(db, ticket, TimerKind.INITIAL_RESPONSE, cycle=2))


def test_timer_level_range(db: Session, ticket: Ticket) -> None:
    timer = make_timer(db, ticket)

    def overflow() -> None:
        timer.level = 4

    _violates(db, overflow)


def test_timer_cycle_positive(db: Session, ticket: Ticket) -> None:
    _violates(db, lambda: make_timer(db, ticket, cycle=0))


def test_active_timer_index_exists(db: Session) -> None:
    definition = db.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_sla_timers_active_due_at'")
    ).scalar_one()
    assert "met_at IS NULL" in definition
    assert "stopped_at IS NULL" in definition
    assert "paused_at IS NULL" in definition


def test_escalation_step_recorded_once(db: Session, ticket: Ticket, requester: User) -> None:
    make_escalation_event(db, ticket, step_key="L2", recipients=[requester])
    make_escalation_event(db, ticket, step_key="L3", level=3)
    make_escalation_event(db, ticket, step_key="L2", cycle=2)
    make_escalation_event(db, ticket, step_key="L2", timer_kind=TimerKind.PROGRESS_UPDATE)
    _violates(db, lambda: make_escalation_event(db, ticket, step_key="L2"))


def test_escalation_recipients_array(db: Session, ticket: Ticket, requester: User) -> None:
    event = make_escalation_event(db, ticket, recipients=[requester])
    db.expire(event)
    assert event.recipient_ids == [requester.id]


@pytest.mark.parametrize("level", [0, 4])
def test_escalation_level_must_be_one_to_three(db: Session, ticket: Ticket, level: int) -> None:
    _violates(db, lambda: make_escalation_event(db, ticket, level=level))


def test_notification_dedupe_key_unique_per_user(
    db: Session, it: Department, requester: User
) -> None:
    other = make_user(db, it)
    make_notification(db, requester, dedupe_key="ticket_created:1")
    make_notification(db, other, dedupe_key="ticket_created:1")
    make_notification(db, requester)
    make_notification(db, requester)
    _violates(db, lambda: make_notification(db, requester, dedupe_key="ticket_created:1"))


def test_collaborator_primary_key(db: Session, it: Department, ticket: Ticket) -> None:
    collaborator = make_user(db, it)
    make_collaborator(db, ticket, collaborator)
    _violates(db, lambda: make_collaborator(db, ticket, collaborator))


def test_ticket_events_are_immutable(db: Session, ticket: Ticket, requester: User) -> None:
    event = make_ticket_event(
        db, ticket, actor=requester, kind=TicketEventKind.COMMENT, body="Hello"
    )
    _violates(
        db,
        lambda: db.execute(
            text("UPDATE ticket_events SET body = 'changed' WHERE id = :id"), {"id": event.id}
        ),
        DBAPIError,
    )
    _violates(
        db,
        lambda: db.execute(text("DELETE FROM ticket_events WHERE id = :id"), {"id": event.id}),
        DBAPIError,
    )
    assert db.scalar(text("SELECT body FROM ticket_events WHERE id = :id"), {"id": event.id}) == (
        "Hello"
    )


def test_attachment_links_later(db: Session, ticket: Ticket, requester: User) -> None:
    attachment = make_attachment(db, requester)
    assert attachment.ticket_id is None
    attachment.ticket_id = ticket.id
    db.flush()
    assert attachment.ticket_id == ticket.id


def test_outbox_defaults(db: Session, requester: User) -> None:
    email = make_outbox_email(db, requester.email)
    stored = db.execute(
        text("SELECT status, attempts FROM email_outbox WHERE id = :id"), {"id": email.id}
    ).one()
    assert tuple(stored) == ("pending", 0)


def test_worker_heartbeat_upsert(db: Session) -> None:
    for offset in (0, 15):
        db.execute(
            text(
                "INSERT INTO worker_heartbeat (name, last_seen_at, details) "
                "VALUES ('main', :at, '{}') "
                "ON CONFLICT (name) DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at"
            ),
            {"at": FACTORY_NOW + timedelta(seconds=offset)},
        )
    seen = db.scalar(text("SELECT last_seen_at FROM worker_heartbeat WHERE name = 'main'"))
    assert seen == FACTORY_NOW + timedelta(seconds=15)


def test_confidential_category_marks_ticket(db: Session, it: Department, requester: User) -> None:
    payroll = make_category(db, it, "Payroll", is_confidential=True)
    ticket = make_ticket(db, requester, it, category=payroll)
    assert ticket.confidential is True
    assert db.scalar(select(Ticket.confidential).where(Ticket.id == ticket.id)) is True
