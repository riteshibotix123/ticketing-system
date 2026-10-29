from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Role, TicketStatus
from app.core.events import CollaboratorChanged, DomainEvent, TeamUpdateRecorded, bus
from app.core.security import create_access_token
from app.models import AuditLog, Category, Department, Ticket, TicketEvent, User
from tests.factories import (
    make_category,
    make_collaborator,
    make_confidential_grant,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_user,
)

TICKETS = "/api/v1/tickets"


@dataclass(frozen=True)
class Team:
    it: Department
    requester: User
    spoke: User
    assignee: User
    collaborator: User
    admin: User
    super_admin: User
    guest: User
    secret: Category


@pytest.fixture
def team(db: Session) -> Team:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    spoke = make_user(db, it, name="Sam Spoke")
    make_spoke_assignment(db, spoke, it)
    return Team(
        it=it,
        requester=make_user(db, hr, name="Rita Requester"),
        spoke=spoke,
        assignee=make_user(db, hr, name="Andy Assignee"),
        collaborator=make_user(db, hr, name="Cora Collaborator"),
        admin=make_user(db, hr, role=Role.ADMIN, name="Ada Admin"),
        super_admin=make_user(db, hr, role=Role.SUPER_ADMIN, name="Sue Super"),
        guest=make_user(db, hr, name="Gus Guest"),
        secret=make_category(db, it, "Investigations", is_confidential=True),
    )


def ticket_in(
    db: Session, team: Team, status: TicketStatus = TicketStatus.IN_PROGRESS, **extra: bool
) -> Ticket:
    category = team.secret if extra.get("confidential") else None
    ticket = make_ticket(
        db,
        team.requester,
        team.it,
        status=status,
        owner=team.spoke,
        assignee=team.assignee,
        category=category,
    )
    make_collaborator(db, ticket, team.collaborator)
    return ticket


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def add(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    actor: User,
    ticket: Ticket,
    user_id: str,
) -> Response:
    response: Response = client.post(
        f"{TICKETS}/{ticket.ticket_no}/collaborators",
        json={"user_id": user_id},
        headers=bearer(db, actor, clock, settings),
    )
    return response


def remove(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    actor: User,
    ticket: Ticket,
    user_id: str,
) -> Response:
    response: Response = client.delete(
        f"{TICKETS}/{ticket.ticket_no}/collaborators/{user_id}",
        headers=bearer(db, actor, clock, settings),
    )
    return response


def view(
    client: TestClient, db: Session, clock: Clock, settings: Settings, user: User, ticket: Ticket
) -> int:
    response: Response = client.get(
        f"{TICKETS}/{ticket.ticket_no}", headers=bearer(db, user, clock, settings)
    )
    return response.status_code


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


def capture(*event_types: type[DomainEvent]) -> list[DomainEvent]:
    seen: list[DomainEvent] = []
    for event_type in event_types:
        bus.register(event_type, lambda _session, event: seen.append(event))
    return seen


def audit_rows(db: Session, ticket: Ticket) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.ticket_id == ticket.id)))


def collaborator_ids(response: Response) -> list[str]:
    return [item["id"] for item in response.json()["collaborators"]]


def test_spoke_adds_collaborator(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team)
    seen = capture(CollaboratorChanged, TeamUpdateRecorded)
    response = add(client, db, clock, settings, team.spoke, ticket, str(team.guest.id))
    assert response.status_code == 200
    assert sorted(collaborator_ids(response)) == sorted(
        [str(team.collaborator.id), str(team.guest.id)]
    )
    [event] = db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id))
    assert (event.action, event.is_public) == ("collaborator_added", False)
    assert event.detail == "Gus Guest added as a collaborator"
    [entry] = audit_rows(db, ticket)
    assert entry.action == "ticket_collaborator_added"
    assert entry.new_value == {"collaborator_id": str(team.guest.id)}
    assert entry.is_security_limited is False
    [changed] = seen
    assert isinstance(changed, CollaboratorChanged)
    assert (changed.user_id, changed.added) == (team.guest.id, True)
    assert view(client, db, clock, settings, team.guest, ticket) == 200


def test_remove_collaborator(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team)
    seen = capture(CollaboratorChanged)
    response = remove(client, db, clock, settings, team.admin, ticket, str(team.collaborator.id))
    assert response.status_code == 200
    assert collaborator_ids(response) == []
    [entry] = audit_rows(db, ticket)
    assert entry.action == "ticket_collaborator_removed"
    assert entry.old_value == {"collaborator_id": str(team.collaborator.id)}
    [changed] = seen
    assert isinstance(changed, CollaboratorChanged)
    assert changed.added is False
    assert view(client, db, clock, settings, team.collaborator, ticket) == 404


def test_duplicate_collaborator_conflicts(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team)
    response = add(client, db, clock, settings, team.spoke, ticket, str(team.collaborator.id))
    assert response.status_code == 409
    assert error_code(response) == "conflict"


@pytest.mark.parametrize("target", ["requester", "inactive", "unknown", "malformed"])
def test_invalid_target(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    target: str,
) -> None:
    ticket = ticket_in(db, team)
    inactive = make_user(db, team.it, state=AccountState.DEACTIVATED)
    user_id = {
        "requester": str(team.requester.id),
        "inactive": str(inactive.id),
        "unknown": "00000000-0000-4000-8000-000000000000",
        "malformed": "not-a-uuid",
    }[target]
    response = add(client, db, clock, settings, team.spoke, ticket, user_id)
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"user_id"}
    assert audit_rows(db, ticket) == []


@pytest.mark.parametrize(
    ("who", "status", "expected"),
    [
        ("requester", TicketStatus.IN_PROGRESS, 403),
        ("collaborator", TicketStatus.IN_PROGRESS, 403),
        ("assignee", TicketStatus.IN_PROGRESS, 403),
        ("guest", TicketStatus.IN_PROGRESS, 404),
        ("spoke", TicketStatus.NEW, 200),
        ("admin", TicketStatus.RESOLVED, 200),
        ("spoke", TicketStatus.CLOSED, 409),
        ("admin", TicketStatus.CANCELLED, 409),
    ],
)
def test_add_permissions(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    who: str,
    status: TicketStatus,
    expected: int,
) -> None:
    ticket = ticket_in(db, team, status)
    target = make_user(db, team.it)
    actor: User = getattr(team, who)
    response = add(client, db, clock, settings, actor, ticket, str(target.id))
    assert response.status_code == expected
    if expected == 403:
        assert error_code(response) == "forbidden"
    if expected == 409:
        assert error_code(response) == "invalid_transition"


def test_remove_permissions_and_missing(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team)
    response = remove(
        client, db, clock, settings, team.requester, ticket, str(team.collaborator.id)
    )
    assert response.status_code == 403
    for user_id in (str(team.guest.id), "not-a-uuid"):
        response = remove(client, db, clock, settings, team.spoke, ticket, user_id)
        assert response.status_code == 404
    assert audit_rows(db, ticket) == []


def test_confidential_ticket_collaborator(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, confidential=True)
    assert view(client, db, clock, settings, team.guest, ticket) == 404
    response = add(client, db, clock, settings, team.spoke, ticket, str(team.guest.id))
    assert response.status_code == 404
    response = add(client, db, clock, settings, team.admin, ticket, str(team.guest.id))
    assert response.status_code == 404
    response = add(client, db, clock, settings, team.super_admin, ticket, str(team.guest.id))
    assert response.status_code == 200
    assert view(client, db, clock, settings, team.guest, ticket) == 200
    assert view(client, db, clock, settings, team.spoke, ticket) == 404
    [entry] = audit_rows(db, ticket)
    assert (entry.is_security_limited, entry.is_confidential_ticket) == (True, True)
    response = remove(client, db, clock, settings, team.super_admin, ticket, str(team.guest.id))
    assert response.status_code == 200
    assert view(client, db, clock, settings, team.guest, ticket) == 404


def test_granted_spoke_manages_confidential_collaborators(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, confidential=True)
    make_confidential_grant(db, team.spoke, team.secret)
    response = add(client, db, clock, settings, team.spoke, ticket, str(team.guest.id))
    assert response.status_code == 200
    assert view(client, db, clock, settings, team.guest, ticket) == 200
