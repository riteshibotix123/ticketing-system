from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import create_access_token
from app.models import TicketEvent, TicketEventKind, User
from tests.factories import FACTORY_NOW, TicketWorld, make_ticket_event, make_ticket_world

TICKETS = "/api/v1/tickets"


@pytest.fixture
def world(db: Session) -> TicketWorld:
    world = make_ticket_world(db)
    ticket = world.tickets["normal"]
    spoke = world.users["spoke"]
    make_ticket_event(db, ticket, actor=None, action="created", at=FACTORY_NOW)
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            at=FACTORY_NOW + timedelta(hours=1),
            actor_id=spoke.id,
            kind=TicketEventKind.AUDIT,
            action="eta_revised",
            detail="ETA moved: vendor delay",
            public_detail="ETA moved",
            is_public=True,
        )
    )
    make_ticket_event(
        db,
        ticket,
        actor=spoke,
        kind=TicketEventKind.INTERNAL_NOTE,
        action=None,
        body="Check the vendor contract",
        is_public=False,
        at=FACTORY_NOW + timedelta(hours=2),
    )
    make_ticket_event(
        db,
        ticket,
        actor=spoke,
        action="priority_changed",
        is_public=False,
        at=FACTORY_NOW + timedelta(hours=3),
    )
    make_ticket_event(
        db,
        ticket,
        actor=world.users["requester"],
        kind=TicketEventKind.COMMENT,
        action=None,
        body="Any update?",
        is_public=True,
        at=FACTORY_NOW + timedelta(hours=4),
    )
    return world


def timeline(
    client: TestClient, db: Session, user: User, clock: Clock, settings: Settings, number: str
) -> Response:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    response: Response = client.get(
        f"{TICKETS}/{number}/timeline", headers={"Authorization": f"Bearer {token}"}
    )
    return response


@pytest.mark.parametrize("name", ["requester", "collaborator"])
def test_requester_and_collaborator_see_public_events_only(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    name: str,
) -> None:
    number = world.tickets["normal"].ticket_no
    body = timeline(client, db, world.users[name], clock, settings, number).json()
    assert [event["type"] for event in body] == ["audit", "audit", "comment"]
    assert body[0]["actor"] == {"id": "system", "name": "System"}
    assert body[1]["detail"] == "ETA moved"
    assert all(event["public"] for event in body)
    assert "vendor" not in str(body).lower()


@pytest.mark.parametrize("name", ["assignee", "spoke", "admin", "super_admin"])
def test_team_and_assignee_see_everything(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    name: str,
) -> None:
    number = world.tickets["normal"].ticket_no
    body = timeline(client, db, world.users[name], clock, settings, number).json()
    assert [event["type"] for event in body] == [
        "audit",
        "audit",
        "internal_note",
        "audit",
        "comment",
    ]
    assert body[1]["detail"] == "ETA moved: vendor delay"
    assert body[2]["body"] == "Check the vendor contract"
    assert body[2]["public"] is False
    assert body[3]["action"] == "priority_changed"
    assert [event["at"] for event in body] == sorted(event["at"] for event in body)


def test_absent_fields_are_omitted(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    number = world.tickets["normal"].ticket_no
    body = timeline(client, db, world.users["spoke"], clock, settings, number).json()
    assert "body" not in body[0]
    assert "action" not in body[2]
    assert set(body[4]) == {"id", "at", "actor", "type", "body", "public"}


@pytest.mark.parametrize("name", ["other_spoke", "unrelated", "employee_with_grant"])
def test_hidden_ticket_timeline_is_404(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    name: str,
) -> None:
    number = world.tickets["normal"].ticket_no
    response = timeline(client, db, world.users[name], clock, settings, number)
    missing = timeline(client, db, world.users[name], clock, settings, "IBX-IT-2026-999998")
    assert response.status_code == missing.status_code == 404
    assert response.json()["error"]["message"] == missing.json()["error"]["message"]


def test_confidential_timeline_hidden_from_spoke_without_grant(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    number = world.tickets["secret"].ticket_no
    assert timeline(client, db, world.users["spoke"], clock, settings, number).status_code == 404
    granted = timeline(client, db, world.users["spoke_with_grant"], clock, settings, number)
    assert granted.status_code == 200
