from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.enums import Role, TicketAction, TicketStatus
from app.core.errors import ApiError, ErrorCode
from app.models import AuditLog, Department, TicketEvent, TicketEventKind, User
from app.policy import Actor
from app.policy.actors import load_actor
from app.services.workflow.common import (
    AuditEntry,
    TimelineEntry,
    Workflow,
    event_data,
    format_time,
    status_label,
)
from tests.factories import make_department, make_spoke_assignment, make_ticket, make_user


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT")


def actor_of(db: Session, user: User) -> Actor:
    actor = load_actor(db, user.id)
    assert actor is not None
    return actor


def test_format_time_uses_ist() -> None:
    assert format_time(datetime(2026, 10, 27, 4, 30, tzinfo=UTC)) == "27 Oct 2026, 10:00 IST"


def test_status_label() -> None:
    assert status_label(TicketStatus.AWAITING_REQUESTER) == "awaiting requester"


def test_event_data_is_json_safe() -> None:
    at = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)
    assert event_data(at=at, status=TicketStatus.NEW, none=None) == {
        "at": "2026-10-27T04:30:00Z",
        "status": "new",
        "none": None,
    }


def test_begin_returns_locked_ticket(db: Session, clock: FrozenClock, it: Department) -> None:
    spoke = make_user(db, it)
    make_spoke_assignment(db, spoke, it)
    ticket = make_ticket(db, make_user(db, it), it)
    locked, ctx, now = Workflow(db, clock).begin(
        actor_of(db, spoke), ticket.ticket_no, TicketAction.ACKNOWLEDGE
    )
    assert locked.id == ticket.id
    assert ctx.is_department_spoke
    assert now == clock.now()


def test_begin_hidden_ticket_is_not_found(db: Session, clock: FrozenClock, it: Department) -> None:
    ticket = make_ticket(db, make_user(db, it), it)
    outsider = actor_of(db, make_user(db, it))
    flow = Workflow(db, clock)
    for number in (ticket.ticket_no, "IBX-IT-2026-999999"):
        with pytest.raises(ApiError) as caught:
            flow.begin(outsider, number, TicketAction.ACKNOWLEDGE)
        assert caught.value.code is ErrorCode.NOT_FOUND


def test_begin_classifies_denials(db: Session, clock: FrozenClock, it: Department) -> None:
    requester = make_user(db, it)
    ticket = make_ticket(db, requester, it)
    admin = actor_of(db, make_user(db, it, role=Role.ADMIN))
    flow = Workflow(db, clock)
    with pytest.raises(ApiError) as wrong_status:
        flow.begin(admin, ticket.ticket_no, TicketAction.RESOLVE)
    assert wrong_status.value.code is ErrorCode.INVALID_TRANSITION
    with pytest.raises(ApiError) as wrong_actor:
        flow.begin(actor_of(db, requester), ticket.ticket_no, TicketAction.ASSIGN)
    assert wrong_actor.value.code is ErrorCode.FORBIDDEN


def test_record_writes_event_and_audit(db: Session, clock: FrozenClock, it: Department) -> None:
    ticket = make_ticket(db, make_user(db, it), it, confidential=True)
    actor = make_user(db, it)
    clock.advance(timedelta(hours=1))
    Workflow(db, clock).record(
        ticket,
        actor.id,
        clock.now(),
        TimelineEntry(action="eta_revised", detail="staff", public_detail="public", public=True),
        AuditEntry(action="ticket_eta_revised", old_value={"a": 1}, new_value={"a": 2}, reason="r"),
    )
    db.flush()
    event = db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)).one()
    assert event.kind is TicketEventKind.AUDIT
    assert (event.detail, event.public_detail, event.is_public) == ("staff", "public", True)
    entry = db.scalars(select(AuditLog).where(AuditLog.ticket_id == ticket.id)).one()
    assert entry.action == "ticket_eta_revised"
    assert entry.object_id == ticket.ticket_no
    assert entry.is_confidential_ticket is True
    assert entry.department_id == "IT"
    assert ticket.updated_at == clock.now()
