import dataclasses
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core import events
from app.core.enums import TicketStatus
from app.core.events import (
    CommentAdded,
    DomainEvent,
    EventBus,
    TicketCreated,
    TicketStatusChanged,
)
from app.models import Department
from app.services.handlers import register_all

AT = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)


def _created() -> TicketCreated:
    return TicketCreated(actor_id=uuid.uuid4(), occurred_at=AT, ticket_id=uuid.uuid4())


def test_events_are_frozen() -> None:
    event = _created()
    field_name = "ticket_id"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(event, field_name, uuid.uuid4())


def test_event_fields() -> None:
    event = TicketStatusChanged(
        actor_id=None,
        occurred_at=AT,
        ticket_id=uuid.uuid4(),
        from_status=TicketStatus.NEW,
        to_status=TicketStatus.ACKNOWLEDGED,
    )
    assert isinstance(event, DomainEvent)
    assert event.from_status is TicketStatus.NEW


def test_handlers_run_in_order(db: Session) -> None:
    bus = EventBus()
    calls: list[str] = []
    bus.register(TicketCreated, lambda _s, _e: calls.append("first"))
    bus.register(TicketCreated, lambda _s, _e: calls.append("second"))
    bus.publish(db, _created())
    assert calls == ["first", "second"]


def test_dispatch_by_exact_type(db: Session) -> None:
    bus = EventBus()
    calls: list[DomainEvent] = []
    bus.register(CommentAdded, lambda _s, event: calls.append(event))
    bus.publish(db, _created())
    assert calls == []


def test_handler_exception_propagates(db: Session) -> None:
    bus = EventBus()
    calls: list[str] = []

    def failing(_session: Session, _event: TicketCreated) -> None:
        raise RuntimeError("boom")

    bus.register(TicketCreated, failing)
    bus.register(TicketCreated, lambda _s, _e: calls.append("after"))
    with pytest.raises(RuntimeError, match="boom"):
        bus.publish(db, _created())
    assert calls == []


def test_handlers_share_caller_transaction(db: Session) -> None:
    bus = EventBus()

    def add_department(session: Session, _event: TicketCreated) -> None:
        session.add(Department(id="EVTX", name="Events", created_at=AT, updated_at=AT))
        session.flush()

    bus.register(TicketCreated, add_department)
    bus.publish(db, _created())
    assert db.get(Department, "EVTX") is not None


def test_register_all_resets_default_bus(db: Session) -> None:
    fresh = EventBus()
    register_all(fresh)
    events.register(TicketCreated, lambda _s, _e: None)
    register_all()
    assert events.bus.handler_count(TicketCreated) == fresh.handler_count(TicketCreated)
    events.publish(db, _created())
