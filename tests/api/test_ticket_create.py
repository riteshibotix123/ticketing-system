import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import events
from app.core.clock import Clock, FrozenClock
from app.core.config import Environment, Settings
from app.core.enums import AccountState, ScanStatus
from app.core.events import TicketCreated
from app.core.security import create_access_token
from app.models import (
    Attachment,
    AuditLog,
    Category,
    Department,
    SlaTimer,
    Ticket,
    TicketEvent,
    TimerKind,
    User,
)
from tests.factories import (
    make_attachment,
    make_category,
    make_department,
    make_spoke_assignment,
    make_user,
)

TICKETS = "/api/v1/tickets"
NUMBER_PATTERN = re.compile(r"^IBX-IT-2026-\d{6}$")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(env=Environment.TEST, max_files_per_ticket=2, attachment_dir=tmp_path)


@pytest.fixture
def it(db: Session) -> Department:
    department = make_department(db, "IT")
    make_spoke_assignment(db, make_user(db, department), department)
    return department


@pytest.fixture
def requester(db: Session, it: Department) -> User:
    return make_user(db, it, name="Requester")


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "department_id": "IT",
        "category_id": None,
        "title": "Laptop will not boot",
        "description": "It shows a black screen.",
        "priority": "high",
        "confidential": False,
        "attachment_ids": [],
    }
    body.update(overrides)
    return body


def create(
    client: TestClient,
    db: Session,
    user: User,
    clock: Clock,
    settings: Settings,
    **overrides: object,
) -> Response:
    response: Response = client.post(
        TICKETS, json=payload(**overrides), headers=bearer(db, user, clock, settings)
    )
    return response


def field_errors(response: Response) -> dict[str, str]:
    assert response.status_code == 422, response.text
    fields = response.json()["error"]["fields"]
    assert isinstance(fields, dict)
    return fields


@pytest.mark.usefixtures("it")
def test_create_ticket(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    requester: User,
) -> None:
    published: list[TicketCreated] = []
    events.register(TicketCreated, lambda _session, event: published.append(event))
    response = create(client, db, requester, clock, settings, title="  Laptop will not boot  ")
    assert response.status_code == 201
    body = response.json()
    assert NUMBER_PATTERN.match(body["id"])
    assert body["title"] == "Laptop will not boot"
    assert body["status"] == "new"
    assert body["priority"] == body["requested_priority"] == "high"
    assert body["confidential"] is False
    assert body["requester"]["id"] == str(requester.id)
    assert body["owner"] is None
    assert body["sla"]["kind"] == "initial_response"
    assert body["allowed_actions"] == ["cancel", "comment"]
    ticket = db.scalars(select(Ticket).where(Ticket.ticket_no == body["id"])).one()
    assert ticket.origin_department_code == "IT"
    assert ticket.sla_started_at == clock.now()
    assert [event.ticket_id for event in published] == [ticket.id]
    timers = list(db.scalars(select(SlaTimer).where(SlaTimer.ticket_id == ticket.id)))
    assert [timer.kind for timer in timers] == [TimerKind.INITIAL_RESPONSE]
    audit = db.scalars(select(AuditLog).where(AuditLog.ticket_id == ticket.id)).one()
    assert audit.action == "ticket_created"
    event = db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)).one()
    assert (event.action, event.is_public, event.actor_id) == ("created", True, requester.id)


@pytest.mark.usefixtures("it")
def test_numbers_increase(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    requester: User,
) -> None:
    first = create(client, db, requester, clock, settings).json()["id"]
    second = create(client, db, requester, clock, settings).json()["id"]
    assert int(second[-6:]) == int(first[-6:]) + 1


@pytest.mark.usefixtures("it")
def test_ist_year_boundary(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    requester: User,
) -> None:
    clock.set(datetime(2026, 12, 31, 18, 29, tzinfo=UTC))
    assert create(client, db, requester, clock, settings).json()["id"].startswith("IBX-IT-2026-")
    clock.set(datetime(2026, 12, 31, 18, 30, tzinfo=UTC))
    assert create(client, db, requester, clock, settings).json()["id"] == "IBX-IT-2027-000001"


@pytest.mark.usefixtures("it")
def test_department_must_accept_tickets(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    requester: User,
) -> None:
    make_department(db, "HR")
    inactive = make_department(db, "FIN", is_active=False)
    make_spoke_assignment(db, make_user(db, inactive), inactive)
    gone = make_department(db, "OPS")
    make_spoke_assignment(db, make_user(db, gone, state=AccountState.DEACTIVATED), gone)
    for code in ("HR", "FIN", "OPS", "NOPE", "it", ""):
        response = create(client, db, requester, clock, settings, department_id=code)
        assert "department_id" in field_errors(response), code


def test_category_rules(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    it: Department,
    requester: User,
) -> None:
    hardware = make_category(db, it, "Hardware")
    retired = make_category(db, it, "Retired", is_active=False)
    hr = make_department(db, "HR")
    make_spoke_assignment(db, make_user(db, hr), hr)
    other = make_category(db, hr, "Payroll")
    assert "category_id" in field_errors(create(client, db, requester, clock, settings))
    for value in (
        str(retired.id),
        str(other.id),
        "not-a-uuid",
        "00000000-0000-4000-8000-000000000001",
    ):
        response = create(client, db, requester, clock, settings, category_id=value)
        assert "category_id" in field_errors(response)
    ok = create(client, db, requester, clock, settings, category_id=str(hardware.id))
    assert ok.status_code == 201
    assert ok.json()["category_name"] == "Hardware"


def test_category_optional_when_department_has_only_inactive_categories(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    it: Department,
    requester: User,
) -> None:
    make_category(db, it, "Retired", is_active=False)
    assert create(client, db, requester, clock, settings).status_code == 201


def test_confidential_category_forces_confidential(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    it: Department,
    requester: User,
) -> None:
    secret: Category = make_category(db, it, "Investigations", is_confidential=True)
    response = create(
        client, db, requester, clock, settings, category_id=str(secret.id), confidential=False
    )
    assert response.json()["confidential"] is True
    hardware = make_category(db, it, "Hardware")
    chosen = create(
        client, db, requester, clock, settings, category_id=str(hardware.id), confidential=True
    )
    assert chosen.json()["confidential"] is True


@pytest.mark.usefixtures("it")
def test_attachments_are_linked(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    requester: User,
) -> None:
    files = [make_attachment(db, requester, ticket=None) for _ in range(2)]
    response = create(
        client, db, requester, clock, settings, attachment_ids=[str(file.id) for file in files]
    )
    assert response.status_code == 201
    assert len(response.json()["attachments"]) == 2
    for file in files:
        db.refresh(file)
        assert file.ticket_id is not None


def test_attachment_rules(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    it: Department,
    requester: User,
) -> None:
    other = make_user(db, it)
    foreign = make_attachment(db, other)
    infected = make_attachment(db, requester, scan_status=ScanStatus.INFECTED)
    mine = [make_attachment(db, requester) for _ in range(3)]
    linked_ticket = create(client, db, requester, clock, settings).json()["id"]
    linked = make_attachment(
        db,
        requester,
        ticket=db.scalars(select(Ticket).where(Ticket.ticket_no == linked_ticket)).one(),
    )
    cases: list[list[str]] = [
        [str(foreign.id)],
        [str(infected.id)],
        [str(linked.id)],
        ["not-a-uuid"],
        ["00000000-0000-4000-8000-000000000002"],
        [str(mine[0].id), str(mine[0].id)],
        [str(item.id) for item in mine],
    ]
    for ids in cases:
        response = create(client, db, requester, clock, settings, attachment_ids=ids)
        assert "attachment_ids" in field_errors(response), ids
    assert db.scalar(select(Attachment.ticket_id).where(Attachment.id == mine[0].id)) is None


@pytest.mark.usefixtures("it")
def test_pending_scan_attachment_can_be_linked(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    requester: User,
) -> None:
    pending = make_attachment(db, requester, scan_status=ScanStatus.PENDING)
    response = create(client, db, requester, clock, settings, attachment_ids=[str(pending.id)])
    assert response.status_code == 201


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"title": ""}, "title"),
        ({"title": "   "}, "title"),
        ({"title": "x" * 121}, "title"),
        ({"description": ""}, "description"),
        ({"description": "x" * 5001}, "description"),
        ({"priority": "urgent"}, "priority"),
        ({"priority": None}, "priority"),
    ],
)
@pytest.mark.usefixtures("it")
def test_body_validation(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    requester: User,
    overrides: dict[str, object],
    field: str,
) -> None:
    response = create(client, db, requester, clock, settings, **overrides)
    assert any(key.endswith(field) for key in field_errors(response))


def test_create_requires_authentication(client: TestClient) -> None:
    assert client.post(TICKETS, json=payload()).status_code == 401
