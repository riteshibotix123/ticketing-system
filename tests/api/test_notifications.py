from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import TicketStatus
from app.core.security import create_access_token
from app.models import Category, Department, EmailOutbox, Notification, Ticket, User
from tests.factories import (
    FACTORY_NOW,
    make_category,
    make_department,
    make_notification,
    make_spoke_assignment,
    make_ticket,
    make_user,
)

NOTIFICATIONS = "/api/v1/notifications"


@dataclass(frozen=True)
class World:
    it: Department
    alice: User
    bob: User
    secret: Category
    ticket: Ticket


@pytest.fixture
def world(db: Session) -> World:
    it = make_department(db, "IT")
    alice = make_user(db, it, name="Alice")
    bob = make_user(db, it, name="Bob")
    return World(
        it=it,
        alice=alice,
        bob=bob,
        secret=make_category(db, it, "Investigations", is_confidential=True),
        ticket=make_ticket(db, alice, it, title="Printer jam"),
    )


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def get(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    user: User,
    path: str,
    **params: str | int | bool,
) -> Response:
    response: Response = client.get(
        f"{NOTIFICATIONS}{path}", params=params, headers=bearer(db, user, clock, settings)
    )
    return response


def post(
    client: TestClient, db: Session, clock: Clock, settings: Settings, user: User, path: str
) -> Response:
    response: Response = client.post(
        f"{NOTIFICATIONS}{path}", headers=bearer(db, user, clock, settings)
    )
    return response


def test_list_own_newest_first(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: World
) -> None:
    older = make_notification(
        db, world.alice, ticket=world.ticket, text="Older", at=FACTORY_NOW - timedelta(hours=2)
    )
    newer = make_notification(
        db,
        world.alice,
        kind="signup_pending",
        text="Newer",
        critical=True,
        read_at=FACTORY_NOW,
        at=FACTORY_NOW - timedelta(hours=1),
    )
    make_notification(db, world.bob, ticket=world.ticket, text="Bob's")
    response = get(client, db, clock, settings, world.alice, "")
    assert response.status_code == 200
    payload = response.json()
    assert (payload["total"], payload["page"], payload["page_size"]) == (2, 1, 25)
    assert payload["items"] == [
        {
            "id": str(newer.id),
            "created_at": "2026-10-27T03:30:00Z",
            "read": True,
            "critical": True,
            "text": "Newer",
            "kind": "signup_pending",
        },
        {
            "id": str(older.id),
            "created_at": "2026-10-27T02:30:00Z",
            "read": False,
            "critical": False,
            "text": "Older",
            "ticket_id": world.ticket.ticket_no,
            "kind": "ticket_created",
        },
    ]


def test_unread_filter_and_paging(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: World
) -> None:
    for index in range(3):
        make_notification(
            db, world.alice, text=f"Unread {index}", at=FACTORY_NOW - timedelta(minutes=index)
        )
    make_notification(db, world.alice, text="Read", read_at=FACTORY_NOW)
    response = get(client, db, clock, settings, world.alice, "", unread=True, page_size=2)
    payload = response.json()
    assert payload["total"] == 3
    assert [item["text"] for item in payload["items"]] == ["Unread 0", "Unread 1"]
    response = get(client, db, clock, settings, world.alice, "", unread=True, page=2, page_size=2)
    assert [item["text"] for item in response.json()["items"]] == ["Unread 2"]
    response = get(client, db, clock, settings, world.alice, "", page_size=101)
    assert response.status_code == 422


def test_unread_count(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: World
) -> None:
    make_notification(db, world.alice)
    make_notification(db, world.alice)
    make_notification(db, world.alice, read_at=FACTORY_NOW)
    make_notification(db, world.bob)
    response = get(client, db, clock, settings, world.alice, "/unread-count")
    assert response.status_code == 200
    assert response.json() == {"count": 2}


def test_notification_for_ticket_no_longer_visible_is_hidden(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: World
) -> None:
    secret = make_ticket(db, world.alice, world.it, category=world.secret)
    make_notification(db, world.bob, ticket=secret, text=f"Update on {secret.ticket_no}")
    make_notification(db, world.bob, text="General")
    response = get(client, db, clock, settings, world.bob, "")
    assert [item["text"] for item in response.json()["items"]] == ["General"]
    response = get(client, db, clock, settings, world.bob, "/unread-count")
    assert response.json() == {"count": 1}


def test_mark_read(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: World
) -> None:
    notification = make_notification(db, world.alice)
    response = post(client, db, clock, settings, world.alice, f"/{notification.id}/read")
    assert response.status_code == 204
    assert response.content == b""
    db.refresh(notification)
    assert notification.read_at == clock.now()
    clock.advance(timedelta(minutes=5))
    response = post(client, db, clock, settings, world.alice, f"/{notification.id}/read")
    assert response.status_code == 204
    db.refresh(notification)
    assert notification.read_at == FACTORY_NOW


@pytest.mark.parametrize("target", ["other", "unknown", "malformed"])
def test_mark_read_not_found(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: World,
    target: str,
) -> None:
    bobs = make_notification(db, world.bob)
    notification_id = {
        "other": str(bobs.id),
        "unknown": "00000000-0000-4000-8000-000000000000",
        "malformed": "nope",
    }[target]
    response = post(client, db, clock, settings, world.alice, f"/{notification_id}/read")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    db.refresh(bobs)
    assert bobs.read_at is None


def test_mark_all_read_only_own(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: World
) -> None:
    mine = [make_notification(db, world.alice) for _ in range(2)]
    bobs = make_notification(db, world.bob)
    response = post(client, db, clock, settings, world.alice, "/read-all")
    assert response.status_code == 204
    for row in [*mine, bobs]:
        db.refresh(row)
    assert all(row.read_at == clock.now() for row in mine)
    assert bobs.read_at is None


def test_requires_authentication(client: TestClient) -> None:
    for response in (
        client.get(NOTIFICATIONS),
        client.get(f"{NOTIFICATIONS}/unread-count"),
        client.post(f"{NOTIFICATIONS}/read-all"),
    ):
        assert response.status_code == 401


def test_comment_flow_notifies_department_spoke(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: World
) -> None:
    spoke = make_user(db, world.it, name="Sam Spoke")
    make_spoke_assignment(db, spoke, world.it)
    ticket = make_ticket(db, world.alice, world.it, status=TicketStatus.IN_PROGRESS)
    response = client.post(
        f"/api/v1/tickets/{ticket.ticket_no}/comments",
        json={"body": "Still broken"},
        headers=bearer(db, world.alice, clock, settings),
    )
    assert response.status_code == 201
    response = get(client, db, clock, settings, spoke, "")
    [item] = response.json()["items"]
    assert item["kind"] == "comment_added"
    assert item["ticket_id"] == ticket.ticket_no
    assert item["text"] == f"New comment on {ticket.ticket_no} from Alice"
    notification = db.scalars(select(Notification).where(Notification.user_id == spoke.id)).one()
    email = db.scalars(
        select(EmailOutbox).where(EmailOutbox.notification_id == notification.id)
    ).one()
    assert email.to_address == spoke.email
    assert "Still broken" in email.body_text
    assert get(client, db, clock, settings, world.alice, "").json()["total"] == 0
