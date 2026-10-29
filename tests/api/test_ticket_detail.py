from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.enums import TicketStatus
from app.core.security import create_access_token
from app.models import User
from tests.factories import (
    FACTORY_NOW,
    WORLD_ACTORS,
    TicketWorld,
    make_attachment,
    make_ticket,
    make_ticket_world,
    make_timer,
)

TICKETS = "/api/v1/tickets"
TICKET_KEYS = {
    "id",
    "title",
    "description",
    "department_id",
    "category_id",
    "category_name",
    "priority",
    "requested_priority",
    "status",
    "confidential",
    "requester",
    "owner",
    "assignee",
    "collaborators",
    "created_at",
    "sla_started_at",
    "acknowledged_at",
    "eta",
    "next_checkpoint_at",
    "last_team_update_at",
    "resolved_at",
    "closed_at",
    "reopen_count",
    "hold",
    "resolution_summary",
    "feedback",
    "sla",
    "allowed_actions",
    "attachments",
}
VISIBLE: dict[str, set[str]] = {
    "normal": {
        "requester",
        "assignee",
        "collaborator",
        "spoke",
        "spoke_with_grant",
        "admin",
        "admin_with_grant",
        "super_admin",
    },
    "secret": {
        "requester",
        "assignee",
        "collaborator",
        "spoke_with_grant",
        "admin_with_grant",
        "super_admin",
        "employee_with_grant",
    },
    "hr": {"requester", "other_spoke", "admin", "admin_with_grant", "super_admin"},
}


@pytest.fixture
def world(db: Session) -> TicketWorld:
    return make_ticket_world(db)


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def fetch(
    client: TestClient, db: Session, user: User, clock: Clock, settings: Settings, number: str
) -> Response:
    response: Response = client.get(
        f"{TICKETS}/{number}", headers=bearer(db, user, clock, settings)
    )
    return response


@pytest.mark.parametrize("ticket_key", sorted(VISIBLE))
@pytest.mark.parametrize("name", WORLD_ACTORS)
def test_detail_visibility_matrix(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    name: str,
    ticket_key: str,
) -> None:
    ticket = world.tickets[ticket_key]
    response = fetch(client, db, world.users[name], clock, settings, ticket.ticket_no)
    if name in VISIBLE[ticket_key]:
        assert response.status_code == 200
        assert response.json()["id"] == ticket.ticket_no
    else:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def strip_request_id(response: Response) -> dict[str, object]:
    body = response.json()
    error = dict(body["error"])
    error.pop("request_id")
    return {"status": response.status_code, "error": error, "headers": len(response.content)}


@pytest.mark.parametrize("name", ["spoke", "admin", "unrelated", "other_spoke"])
def test_missing_and_hidden_return_identical_404(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    name: str,
) -> None:
    user = world.users[name]
    hidden = fetch(client, db, user, clock, settings, world.tickets["secret"].ticket_no)
    missing = fetch(client, db, user, clock, settings, "IBX-IT-2026-999999")
    garbage = fetch(client, db, user, clock, settings, "not-a-ticket")
    assert strip_request_id(hidden) == strip_request_id(missing) == strip_request_id(garbage)
    assert world.tickets["secret"].ticket_no not in hidden.text
    assert "Sensitive" not in hidden.text


def test_detail_shape(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    ticket = world.tickets["normal"]
    make_attachment(db, world.users["requester"], ticket=ticket)
    make_timer(db, ticket, started_at=FACTORY_NOW, due_in=timedelta(hours=24))
    body = fetch(client, db, world.users["spoke"], clock, settings, ticket.ticket_no).json()
    assert set(body) == TICKET_KEYS
    assert body["category_id"] == str(world.normal_category.id)
    assert body["category_name"] == "Hardware"
    assert body["requester"]["id"] == str(world.users["requester"].id)
    assert body["assignee"]["name"] == "Assignee"
    assert body["owner"] is not None
    assert [user["name"] for user in body["collaborators"]] == ["Collaborator"]
    assert body["hold"] is None
    assert body["feedback"] is None
    assert len(body["attachments"]) == 1
    assert set(body["attachments"][0]) == {"id", "name", "size", "mime", "scan_status"}
    assert body["sla"]["kind"] == "initial_response"
    assert "resolve" in body["allowed_actions"]


def test_detail_hold_feedback_and_requester_actions(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    held = make_ticket(db, requester, world.it, status=TicketStatus.ON_HOLD)
    closed = world.tickets["closed"]
    closed.feedback_rating = 4
    closed.feedback_comment = "Quick fix"
    db.flush()
    held_body = fetch(client, db, requester, clock, settings, held.ticket_no).json()
    assert held_body["hold"]["reason"] == "Waiting for vendor"
    assert held_body["sla"]["label"] == "Timer paused"
    assert held_body["allowed_actions"] == ["comment"]
    closed_body = fetch(client, db, requester, clock, settings, closed.ticket_no).json()
    assert closed_body["feedback"] == {"rating": 4, "comment": "Quick fix"}
    assert closed_body["sla"]["stopped"] is True


def test_allowed_actions_differ_by_actor(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    number = world.tickets["normal"].ticket_no
    actions = {
        name: fetch(client, db, world.users[name], clock, settings, number).json()[
            "allowed_actions"
        ]
        for name in ("requester", "collaborator", "assignee", "spoke")
    }
    assert actions["requester"] == ["comment"]
    assert actions["collaborator"] == ["comment"]
    assert "internal_note" in actions["assignee"]
    assert "assign" not in actions["assignee"]
    assert "assign" in actions["spoke"]


def test_detail_requires_authentication(client: TestClient, world: TicketWorld) -> None:
    response = client.get(f"{TICKETS}/{world.tickets['normal'].ticket_no}")
    assert response.status_code == 401
