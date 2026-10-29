from collections.abc import Mapping
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Role, TicketStatus
from app.core.events import DomainEvent, TicketTransferred, bus
from app.core.security import create_access_token
from app.models import AuditLog, Category, Department, Ticket, TicketEvent, User
from tests.factories import (
    make_category,
    make_collaborator,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_user,
)

TICKETS = "/api/v1/tickets"
REASON = "Belongs to facilities"


@dataclass(frozen=True)
class Team:
    it: Department
    fac: Department
    requester: User
    spoke: User
    fac_spoke: User
    assignee: User
    collaborator: User
    super_admin: User
    outsider: User


@pytest.fixture
def team(db: Session) -> Team:
    it = make_department(db, "IT")
    fac = make_department(db, "FAC")
    hr = make_department(db, "HR")
    spoke = make_user(db, it, name="Sam Spoke")
    fac_spoke = make_user(db, fac, name="Fay Facilities")
    make_spoke_assignment(db, spoke, it)
    make_spoke_assignment(db, fac_spoke, fac)
    return Team(
        it=it,
        fac=fac,
        requester=make_user(db, hr, name="Rita Requester"),
        spoke=spoke,
        fac_spoke=fac_spoke,
        assignee=make_user(db, hr, name="Andy Assignee"),
        collaborator=make_user(db, hr, name="Cora Collaborator"),
        super_admin=make_user(db, hr, role=Role.SUPER_ADMIN, name="Sue Super"),
        outsider=make_user(db, hr, name="Otto Outsider"),
    )


def ticket_in(
    db: Session,
    team: Team,
    status: TicketStatus,
    *,
    category: Category | None = None,
    confidential: bool = False,
) -> Ticket:
    ticket = make_ticket(
        db,
        team.requester,
        team.it,
        status=status,
        owner=team.spoke,
        assignee=team.assignee,
        category=category,
        confidential=confidential,
    )
    make_collaborator(db, ticket, team.collaborator)
    return ticket


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def transfer(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    user: User,
    ticket: Ticket,
    body: Mapping[str, object],
) -> Response:
    response: Response = client.post(
        f"{TICKETS}/{ticket.ticket_no}/transfer",
        json=body,
        headers=bearer(db, user, clock, settings),
    )
    return response


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


def fields(response: Response) -> set[str]:
    assert response.status_code == 422
    return set(response.json()["error"]["fields"])


def capture() -> list[DomainEvent]:
    seen: list[DomainEvent] = []
    bus.register(TicketTransferred, lambda _session, event: seen.append(event))
    return seen


def to_fac(**extra: object) -> dict[str, object]:
    return {"department_id": "FAC", "reason": REASON, **extra}


@pytest.mark.parametrize(
    "status", [TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD]
)
def test_transfer_side_effects(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    status: TicketStatus,
) -> None:
    ticket = ticket_in(db, team, status)
    number = ticket.ticket_no
    seen = capture()
    response = transfer(client, db, clock, settings, team.spoke, ticket, to_fac())
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == number
    assert payload["department_id"] == "FAC"
    assert payload["status"] == "new"
    for key in ("owner", "assignee", "eta", "next_checkpoint_at", "hold", "category_id"):
        assert payload[key] is None
    assert payload["sla_started_at"] == "2026-10-27T04:30:00Z"
    assert payload["sla"]["kind"] == "initial_response"
    assert payload["allowed_actions"] == []
    db.refresh(ticket)
    assert ticket.origin_department_code == "IT"
    assert (ticket.awaiting_since, ticket.hold_reason, ticket.hold_review_date) == (
        None,
        None,
        None,
    )
    event = db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)).one()
    assert event.action == "transferred"
    assert event.is_public is True
    assert event.detail == f"Transferred from IT to FAC. Reason: {REASON}"
    assert event.public_detail == "Transferred from IT to FAC"
    entry = db.scalars(select(AuditLog).where(AuditLog.ticket_id == ticket.id)).one()
    assert (entry.action, entry.reason) == ("ticket_transferred", REASON)
    [moved] = seen
    assert isinstance(moved, TicketTransferred)
    assert (moved.from_department, moved.to_department) == ("IT", "FAC")


def test_transfer_moves_access(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    assert transfer(client, db, clock, settings, team.spoke, ticket, to_fac()).status_code == 200
    url = f"{TICKETS}/{ticket.ticket_no}"
    assert client.get(url, headers=bearer(db, team.spoke, clock, settings)).status_code == 404
    assert client.get(url, headers=bearer(db, team.assignee, clock, settings)).status_code == 404
    for user in (team.requester, team.collaborator):
        assert client.get(url, headers=bearer(db, user, clock, settings)).status_code == 200
    received = client.get(url, headers=bearer(db, team.fac_spoke, clock, settings))
    assert received.status_code == 200
    assert "acknowledge" in received.json()["allowed_actions"]


def test_transfer_target_rules(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    closed_dept = make_department(db, "OPS", is_active=False)
    make_spoke_assignment(db, make_user(db, closed_dept), closed_dept)
    make_department(db, "LEGAL")
    retired = make_department(db, "SALES")
    make_spoke_assignment(db, make_user(db, retired, state=AccountState.DEACTIVATED), retired)
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    for department_id in ("IT", "OPS", "LEGAL", "SALES", "NOPE", ""):
        body = {"department_id": department_id, "reason": REASON}
        assert fields(transfer(client, db, clock, settings, team.spoke, ticket, body)) == {
            "department_id"
        }
    short = to_fac(reason="abc")
    assert fields(transfer(client, db, clock, settings, team.spoke, ticket, short)) == {"reason"}


def test_transfer_category_rules(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    desks = make_category(db, team.fac, "Desks")
    retired = make_category(db, team.fac, "Old", is_active=False)
    foreign = make_category(db, team.it, "Laptops")
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    for category_id in (None, str(retired.id), str(foreign.id), "not-a-uuid"):
        body = to_fac(category_id=category_id)
        assert fields(transfer(client, db, clock, settings, team.spoke, ticket, body)) == {
            "category_id"
        }
    body = to_fac(category_id=str(desks.id))
    response = transfer(client, db, clock, settings, team.spoke, ticket, body)
    assert response.status_code == 200
    payload = response.json()
    assert (payload["category_id"], payload["category_name"]) == (str(desks.id), "Desks")
    assert payload["confidential"] is False


def test_confidential_category_upgrades_ticket(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    secret = make_category(db, team.fac, "Investigations", is_confidential=True)
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    body = to_fac(category_id=str(secret.id))
    response = transfer(client, db, clock, settings, team.spoke, ticket, body)
    assert response.status_code == 200
    assert response.json()["confidential"] is True
    url = f"{TICKETS}/{ticket.ticket_no}"
    assert client.get(url, headers=bearer(db, team.fac_spoke, clock, settings)).status_code == 404


def test_confidential_is_never_downgraded(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    desks = make_category(db, team.fac, "Desks")
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS, confidential=True)
    body = to_fac(category_id=str(desks.id))
    response = transfer(client, db, clock, settings, team.super_admin, ticket, body)
    assert response.status_code == 200
    assert response.json()["confidential"] is True
    db.refresh(ticket)
    assert ticket.confidential is True


def test_transfer_denials(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    for user in (team.requester, team.assignee, team.collaborator):
        response = transfer(client, db, clock, settings, user, ticket, to_fac())
        assert error_code(response) == "forbidden"
    assert transfer(client, db, clock, settings, team.outsider, ticket, to_fac()).status_code == (
        404
    )
    assert transfer(client, db, clock, settings, team.fac_spoke, ticket, to_fac()).status_code == (
        404
    )
    for status in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED):
        finished = ticket_in(db, team, status)
        response = transfer(client, db, clock, settings, team.spoke, finished, to_fac())
        assert error_code(response) == "invalid_transition"
