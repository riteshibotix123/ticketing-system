from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.security import create_access_token
from app.models import Ticket, User
from app.services.audit import AuditService
from tests.factories import FACTORY_NOW, TicketWorld, make_ticket_world

AUDIT = "/api/v1/audit"


@pytest.fixture
def world(db: Session) -> TicketWorld:
    return make_ticket_world(db)


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def fetch(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    user: User,
    **params: str | int,
) -> Response:
    response: Response = client.get(AUDIT, params=params, headers=bearer(db, user, clock, settings))
    return response


def record(
    db: Session,
    action: str,
    *,
    minutes: int = 0,
    actor: User | None = None,
    ticket: Ticket | None = None,
    detail: str | None = None,
    security_limited: bool = False,
) -> str:
    clock = FrozenClock(FACTORY_NOW - timedelta(minutes=minutes))
    entry = AuditService(db, clock).record(
        action=action,
        object_type="ticket" if ticket else "user",
        object_id=ticket.ticket_no if ticket else None,
        actor_id=actor.id if actor else None,
        new_value={"status": "new"} if ticket else None,
        detail=detail,
        ticket_id=ticket.id if ticket else None,
        department_id=ticket.department_id if ticket else None,
        is_security_limited=security_limited,
        is_confidential_ticket=bool(ticket and ticket.confidential),
    )
    return str(entry.id)


def actions(response: Response) -> list[str]:
    assert response.status_code == 200
    return [item["action"] for item in response.json()["items"]]


@pytest.mark.parametrize(
    ("who", "status"),
    [("requester", 403), ("spoke", 403), ("unrelated", 403), ("admin", 200), ("super_admin", 200)],
)
def test_requires_audit_flag(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    who: str,
    status: int,
) -> None:
    response = fetch(client, db, clock, settings, world.users[who])
    assert response.status_code == status
    if status == 403:
        assert response.json()["error"]["code"] == "forbidden"


def test_scope_per_role(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    record(db, "user_activated", minutes=5)
    record(db, "admin_promoted", minutes=4, security_limited=True)
    record(db, "ticket_created", minutes=3, ticket=world.tickets["normal"])
    record(db, "ticket_resolved", minutes=2, ticket=world.tickets["secret"])
    assert actions(fetch(client, db, clock, settings, world.users["super_admin"])) == [
        "ticket_resolved",
        "ticket_created",
        "admin_promoted",
        "user_activated",
    ]
    assert actions(fetch(client, db, clock, settings, world.users["admin"])) == [
        "ticket_created",
        "user_activated",
    ]
    assert actions(fetch(client, db, clock, settings, world.users["admin_with_grant"])) == [
        "ticket_resolved",
        "ticket_created",
        "user_activated",
    ]


def test_entry_shape(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    ticket = world.tickets["normal"]
    entry_id = record(db, "ticket_created", actor=world.users["requester"], ticket=ticket)
    system_id = record(db, "user_activated", minutes=1)
    items = fetch(client, db, clock, settings, world.users["super_admin"]).json()["items"]
    assert items[0] == {
        "id": entry_id,
        "at": "2026-10-27T04:30:00Z",
        "actor": {
            "id": str(world.users["requester"].id),
            "name": "Requester",
            "email": world.users["requester"].email,
        },
        "action": "ticket_created",
        "object_type": "ticket",
        "object_id": ticket.ticket_no,
        "new_value": {"status": "new"},
    }
    assert items[1] == {
        "id": system_id,
        "at": "2026-10-27T04:29:00Z",
        "actor": {"id": "system", "name": "System"},
        "action": "user_activated",
        "object_type": "user",
        "object_id": None,
    }


def test_filters(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    admin = world.users["admin"]
    normal = world.tickets["normal"]
    record(db, "ticket_created", minutes=50, actor=admin, ticket=normal)
    record(db, "ticket_assigned", minutes=40, ticket=world.tickets["hr"], detail="Moved to Payroll")
    record(db, "user_activated", minutes=30, actor=admin)
    record(db, "login_failed", minutes=10)
    super_admin = world.users["super_admin"]

    def run(**params: str | int) -> list[str]:
        return actions(fetch(client, db, clock, settings, super_admin, **params))

    assert run(q="PAYROLL") == ["ticket_assigned"]
    assert run(q="activated") == ["user_activated"]
    assert run(actor_id=str(admin.id)) == ["user_activated", "ticket_created"]
    assert run(action="login_failed") == ["login_failed"]
    assert run(ticket_id=normal.ticket_no) == ["ticket_created"]
    assert run(**{"from": "2026-10-27T03:45:00Z", "to": "2026-10-27T04:05:00Z"}) == [
        "user_activated",
        "ticket_assigned",
    ]
    paged = fetch(client, db, clock, settings, super_admin, page=2, page_size=3).json()
    assert (paged["total"], [item["action"] for item in paged["items"]]) == (4, ["ticket_created"])
    response = fetch(client, db, clock, settings, super_admin, actor_id="nope")
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"actor_id"}


def test_admin_cannot_find_hidden_ticket_entries_by_number(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    secret = world.tickets["secret"]
    record(db, "ticket_created", ticket=secret)
    response = fetch(client, db, clock, settings, world.users["admin"], ticket_id=secret.ticket_no)
    assert response.json()["total"] == 0
    assert secret.ticket_no not in response.text
