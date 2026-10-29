import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.enums import Priority
from app.core.request_context import (
    RequestContext,
    reset_request_context,
    set_request_context,
)
from app.models import AuditLog, Department, Ticket, TicketEventKind, User
from app.services.audit import AuditService, to_json_value
from tests.factories import make_department, make_ticket, make_ticket_event, make_user


@dataclass(frozen=True)
class Sample:
    priority: Priority
    at: datetime


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT")


@pytest.fixture
def actor(db: Session, it: Department) -> User:
    return make_user(db, it)


@pytest.fixture
def ticket(db: Session, it: Department, actor: User) -> Ticket:
    return make_ticket(db, actor, it)


def test_json_value_conversion() -> None:
    ident = uuid.uuid4()
    at = datetime(2026, 10, 27, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert to_json_value(Priority.HIGH) == "high"
    assert to_json_value(at) == "2026-10-27T04:30:00Z"
    assert to_json_value(date(2026, 10, 27)) == "2026-10-27"
    assert to_json_value(ident) == str(ident)
    assert to_json_value(Decimal("1.50")) == "1.50"
    assert to_json_value({"ids": (ident,), "n": 1, "ok": True, "none": None}) == {
        "ids": [str(ident)],
        "n": 1,
        "ok": True,
        "none": None,
    }
    assert to_json_value(frozenset({"b", "a"})) == ["a", "b"]
    assert to_json_value(Sample(Priority.LOW, at)) == {
        "priority": "low",
        "at": "2026-10-27T04:30:00Z",
    }


@pytest.mark.parametrize("value", [object(), float("nan"), datetime(2026, 1, 1)])
def test_json_value_rejects_unsafe(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        to_json_value(value)


def test_record_uses_clock_and_context(
    db: Session, clock: FrozenClock, actor: User, ticket: Ticket
) -> None:
    token = set_request_context(RequestContext("req-1", "10.0.0.5", "pytest-agent"))
    try:
        entry = AuditService(db, clock).record(
            action="priority_changed",
            object_type="ticket",
            object_id=ticket.ticket_no,
            actor_id=actor.id,
            old_value=Priority.LOW,
            new_value={"priority": Priority.HIGH},
            reason="Customer impact",
            ticket_id=ticket.id,
            department_id="IT",
            is_confidential_ticket=True,
        )
    finally:
        reset_request_context(token)
    db.expire_all()
    stored = db.scalars(select(AuditLog).where(AuditLog.id == entry.id)).one()
    assert stored.created_at == clock.now()
    assert stored.ip_address == "10.0.0.5"
    assert stored.user_agent == "pytest-agent"
    assert stored.old_value == "low"
    assert stored.new_value == {"priority": "high"}
    assert stored.object_id == ticket.ticket_no
    assert stored.is_confidential_ticket is True
    assert stored.is_security_limited is False


def test_record_without_context_stores_sql_null(db: Session, clock: FrozenClock) -> None:
    entry = AuditService(db, clock).record(action="policy_changed", object_type="policy")
    row = db.execute(
        text("SELECT old_value IS NULL, ip_address, actor_id FROM audit_log WHERE id = :id"),
        {"id": entry.id},
    ).one()
    assert tuple(row) == (True, None, None)
    assert entry.created_at == datetime(2026, 10, 27, 4, 30, tzinfo=UTC)


def _blocked(db: Session, sql: str, ident: uuid.UUID) -> None:
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(text(sql), {"id": ident})


def test_audit_log_is_immutable(db: Session, clock: FrozenClock) -> None:
    entry = AuditService(db, clock).record(action="login_success", object_type="user", detail="ok")
    _blocked(db, "UPDATE audit_log SET detail = 'changed' WHERE id = :id", entry.id)
    _blocked(db, "DELETE FROM audit_log WHERE id = :id", entry.id)
    detail = db.scalar(text("SELECT detail FROM audit_log WHERE id = :id"), {"id": entry.id})
    assert detail == "ok"


def test_ticket_events_remain_immutable(db: Session, ticket: Ticket, actor: User) -> None:
    event = make_ticket_event(db, ticket, actor=actor, kind=TicketEventKind.COMMENT, body="Hi")
    _blocked(db, "UPDATE ticket_events SET body = 'x' WHERE id = :id", event.id)
    _blocked(db, "DELETE FROM ticket_events WHERE id = :id", event.id)


@pytest.mark.parametrize("table", ["audit_log", "ticket_events"])
def test_public_cannot_update_or_delete(db: Session, table: str) -> None:
    granted = db.scalar(
        text(
            "SELECT count(*) FROM information_schema.role_table_grants "
            "WHERE grantee = 'PUBLIC' AND table_name = :table "
            "AND privilege_type IN ('UPDATE', 'DELETE')"
        ),
        {"table": table},
    )
    assert granted == 0
