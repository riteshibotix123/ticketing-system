from collections.abc import Mapping
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
from app.models import SavedView, User
from app.services import saved_views
from tests.factories import TicketWorld, make_ticket, make_ticket_world

VIEWS = "/api/v1/saved-views"
TICKETS = "/api/v1/tickets"
BUILT_IN_ALL = [
    "builtin.no_update_24h",
    "builtin.unassigned_today",
    "builtin.escalated_l3",
    "builtin.awaiting_requester_48h",
]


@pytest.fixture
def world(db: Session) -> TicketWorld:
    return make_ticket_world(db)


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


class Api:
    def __init__(
        self, client: TestClient, db: Session, clock: Clock, settings: Settings, user: User
    ) -> None:
        self._client = client
        self._db = db
        self._clock = clock
        self._settings = settings
        self._user = user

    def _headers(self) -> dict[str, str]:
        return bearer(self._db, self._user, self._clock, self._settings)

    def get(self, path: str = VIEWS, params: Mapping[str, object] | None = None) -> Response:
        response: Response = self._client.get(
            path, params=dict(params or {}), headers=self._headers()
        )
        return response

    def post(self, body: Mapping[str, object]) -> Response:
        response: Response = self._client.post(VIEWS, json=dict(body), headers=self._headers())
        return response

    def patch(self, view_id: str, body: Mapping[str, object]) -> Response:
        response: Response = self._client.patch(
            f"{VIEWS}/{view_id}", json=dict(body), headers=self._headers()
        )
        return response

    def delete(self, view_id: str) -> Response:
        response: Response = self._client.delete(f"{VIEWS}/{view_id}", headers=self._headers())
        return response


def api_for(client: TestClient, db: Session, clock: Clock, settings: Settings, user: User) -> Api:
    return Api(client, db, clock, settings, user)


def created(response: Response) -> dict[str, object]:
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_built_in_views_follow_the_role(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    spoke = api_for(client, db, clock, settings, world.users["spoke"]).get().json()
    assert [view["id"] for view in spoke] == ["builtin.department_breached", *BUILT_IN_ALL]
    assert spoke[0] == {
        "id": "builtin.department_breached",
        "name": "My Department - SLA Breached",
        "built_in": True,
        "query": {"scope": "queue", "sla_state": "breached"},
        "created_at": None,
        "updated_at": None,
    }
    by_id = {view["id"]: view for view in spoke}
    assert by_id["builtin.unassigned_today"]["query"] == {
        "scope": "queue",
        "unassigned": True,
        "created_from": "2026-10-26T18:30:00Z",
    }
    assert by_id["builtin.awaiting_requester_48h"]["query"] == {
        "scope": "queue",
        "awaiting_before": "2026-10-25T04:30:00Z",
    }
    admin = api_for(client, db, clock, settings, world.users["admin"]).get().json()
    assert [view["id"] for view in admin] == BUILT_IN_ALL
    assert admin[0]["query"] == {"scope": "all", "sla_state": "stale"}
    employee = api_for(client, db, clock, settings, world.users["requester"]).get().json()
    assert employee[2]["query"] == {"scope": "mine", "escalation_level": 3}


def test_no_update_view_returns_only_stale_tickets(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    stale = make_ticket(
        db, world.users["requester"], world.it, status=TicketStatus.IN_PROGRESS, update_overdue=True
    )
    admin = api_for(client, db, clock, settings, world.users["admin"])
    view = next(v for v in admin.get().json() if v["id"] == "builtin.no_update_24h")
    tickets = admin.get(TICKETS, view["query"]).json()
    assert [ticket["id"] for ticket in tickets["items"]] == [stale.ticket_no]


def test_create_list_update_and_delete_own_view(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    api = api_for(client, db, clock, settings, world.users["spoke"])
    body = created(
        api.post(
            {
                "name": "  Critical in IT  ",
                "query": {
                    "scope": "queue",
                    "priority": ["critical", "high"],
                    "status": ["open"],
                    "created_from": "2026-10-01T00:00:00+05:30",
                },
            }
        )
    )
    assert body["name"] == "Critical in IT"
    assert body["built_in"] is False
    assert body["query"] == {
        "scope": "queue",
        "priority": ["critical", "high"],
        "status": ["open"],
        "created_from": "2026-09-30T18:30:00Z",
    }
    assert body["created_at"] == body["updated_at"] == "2026-10-27T04:30:00Z"
    view_id = str(body["id"])
    created(api.post({"name": "Another", "query": {}}))
    listed = [view["name"] for view in api.get().json() if not view["built_in"]]
    assert listed == ["Another", "Critical in IT"]
    clock.advance(timedelta(hours=1))
    renamed = api.patch(view_id, {"name": "Critical tickets", "query": {"sla_state": "breached"}})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["query"] == {"sla_state": "breached"}
    assert renamed.json()["updated_at"] == "2026-10-27T05:30:00Z"
    assert api.delete(view_id).status_code == 204
    assert [view["name"] for view in api.get().json() if not view["built_in"]] == ["Another"]
    row = db.scalars(select(SavedView).where(SavedView.name == "Critical tickets")).one()
    assert row.deleted_at is not None
    assert api.delete(view_id).status_code == 404


def test_other_users_views_are_invisible(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    owner = api_for(client, db, clock, settings, world.users["spoke"])
    view_id = str(created(owner.post({"name": "Mine only", "query": {}}))["id"])
    other = api_for(client, db, clock, settings, world.users["admin"])
    assert all(view["built_in"] for view in other.get().json())
    for response in (other.patch(view_id, {"name": "Stolen"}), other.delete(view_id)):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    assert owner.patch("not-a-uuid", {"name": "Whatever"}).status_code == 404
    assert owner.delete("builtin.unknown").status_code == 404


def test_built_in_views_cannot_change(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    api = api_for(client, db, clock, settings, world.users["admin"])
    for response in (
        api.patch("builtin.escalated_l3", {"name": "Mine now"}),
        api.delete("builtin.no_update_24h"),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


def test_names_are_unique_per_user_ignoring_case(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    api = api_for(client, db, clock, settings, world.users["requester"])
    first = str(created(api.post({"name": "Waiting", "query": {}}))["id"])
    duplicate = api.post({"name": "WAITING", "query": {}})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"
    second = str(created(api.post({"name": "Other", "query": {}}))["id"])
    assert api.patch(second, {"name": "waiting"}).status_code == 409
    assert api.patch(first, {"name": "waiting"}).status_code == 200
    assert api.delete(first).status_code == 204
    created(api.post({"name": "Waiting", "query": {}}))
    created(
        api_for(client, db, clock, settings, world.users["unrelated"]).post(
            {"name": "Waiting", "query": {}}
        )
    )


def test_view_limit_per_user(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(saved_views, "MAX_VIEWS_PER_USER", 2)
    api = api_for(client, db, clock, settings, world.users["requester"])
    created(api.post({"name": "One", "query": {}}))
    created(api.post({"name": "Two", "query": {}}))
    third = api.post({"name": "Three", "query": {}})
    assert third.status_code == 409


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "x", "query": {}}, "name"),
        ({"name": "y" * 81, "query": {}}, "name"),
        ({"name": "Bad key", "query": {"page": 2}}, "query.page"),
        ({"name": "Bad scope", "query": {"scope": "everything"}}, "query.scope"),
        ({"name": "Bad status", "query": {"status": ["bogus"]}}, "query.status"),
        ({"name": "Bad priority", "query": {"priority": ["urgent"]}}, "query.priority"),
        ({"name": "Bad level", "query": {"escalation_level": 4}}, "query.escalation_level"),
        ({"name": "Bad id", "query": {"assignee_id": "nope"}}, "query.assignee_id"),
        ({"name": "Bad sort", "query": {"sort": "requester"}}, "query.sort"),
        (
            {"name": "Naive", "query": {"awaiting_before": "2026-10-25T00:00:00"}},
            "query.awaiting_before",
        ),
    ],
)
def test_invalid_views_give_field_errors(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    body: dict[str, object],
    field: str,
) -> None:
    response = api_for(client, db, clock, settings, world.users["requester"]).post(body)
    assert response.status_code == 422, response.text
    assert field in response.json()["error"]["fields"]
