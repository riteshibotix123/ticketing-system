from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import Role
from app.core.security import create_access_token
from app.models import AuditLog, Department, Holiday, User
from tests.factories import make_department, make_spoke_assignment, make_user

CALENDAR = "/api/v1/calendar"
HOLIDAYS = f"{CALENDAR}/holidays"
DEFAULT_CALENDAR = {
    "timezone": "Asia/Kolkata",
    "working_days": [1, 2, 3, 4, 5],
    "work_start": "09:00",
    "work_end": "18:00",
    "holidays": [],
    "updated_at": None,
}
HOURS = {"working_days": [6, 1, 2, 3, 4, 5], "work_start": "10:00", "work_end": "17:30"}


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


class Api:
    def __init__(self, client: TestClient, headers: dict[str, str]) -> None:
        self._client = client
        self._headers = headers

    def get(self) -> Response:
        response: Response = self._client.get(CALENDAR, headers=self._headers)
        return response

    def put(self, body: Mapping[str, object]) -> Response:
        response: Response = self._client.put(CALENDAR, json=dict(body), headers=self._headers)
        return response

    def add(self, body: Mapping[str, object]) -> Response:
        response: Response = self._client.post(HOLIDAYS, json=dict(body), headers=self._headers)
        return response

    def remove(self, day: str) -> Response:
        response: Response = self._client.delete(f"{HOLIDAYS}/{day}", headers=self._headers)
        return response


def api_as(client: TestClient, db: Session, clock: Clock, settings: Settings, user: User) -> Api:
    return Api(client, bearer(db, user, clock, settings))


def actions(db: Session) -> list[str]:
    statement = select(AuditLog.action).where(
        AuditLog.action.in_(["business_calendar_updated", "holiday_added", "holiday_removed"])
    )
    return sorted(db.scalars(statement))


def test_defaults_are_readable_by_admins_only(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    for role in (Role.ADMIN, Role.SUPER_ADMIN):
        response = api_as(client, db, clock, settings, make_user(db, it, role=role)).get()
        assert response.status_code == 200, response.text
        assert response.json() == DEFAULT_CALENDAR
    spoke = make_user(db, it)
    make_spoke_assignment(db, spoke, it)
    for user in (spoke, make_user(db, it)):
        response = api_as(client, db, clock, settings, user).get()
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


def test_super_admin_updates_working_hours(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    api = api_as(client, db, clock, settings, super_admin)
    response = api.put(HOURS)
    assert response.status_code == 200, response.text
    assert response.json() == {
        **DEFAULT_CALENDAR,
        "working_days": [1, 2, 3, 4, 5, 6],
        "work_start": "10:00",
        "work_end": "17:30",
        "updated_at": "2026-10-27T04:30:00Z",
    }
    assert api.get().json() == response.json()
    assert api.put(HOURS).status_code == 200
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "business_calendar_updated")).one()
    assert entry.actor_id == super_admin.id
    assert entry.object_type == "business_calendar"
    assert entry.old_value == {
        "working_days": [1, 2, 3, 4, 5],
        "work_start": "09:00",
        "work_end": "18:00",
    }
    assert entry.new_value == {
        "working_days": [1, 2, 3, 4, 5, 6],
        "work_start": "10:00",
        "work_end": "17:30",
    }


def test_admin_cannot_change_the_calendar(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    api = api_as(client, db, clock, settings, make_user(db, it, role=Role.ADMIN))
    for response in (
        api.put(HOURS),
        api.add({"date": "2026-11-09", "name": "Diwali"}),
        api.remove("2026-11-09"),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
    assert actions(db) == []


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"work_start": "18:00", "work_end": "09:00"}, "work_end"),
        ({"work_start": "09:00", "work_end": "09:00"}, "work_end"),
        ({"working_days": []}, "working_days"),
        ({"working_days": [0, 1]}, "working_days"),
        ({"working_days": [1, 8]}, "working_days"),
        ({"working_days": [1, 1]}, "working_days"),
        ({"working_days": [1, 2, 3, 4, 5, 6, 7, 1]}, "working_days"),
        ({"work_start": "9:00"}, "work_start"),
        ({"work_end": "24:00"}, "work_end"),
        ({"work_end": "18:00:00"}, "work_end"),
    ],
)
def test_calendar_validation(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    changes: dict[str, object],
    field: str,
) -> None:
    api = api_as(client, db, clock, settings, make_user(db, it, role=Role.SUPER_ADMIN))
    response = api.put({**HOURS, **changes})
    assert response.status_code == 422, response.text
    assert field in response.json()["error"]["fields"]
    assert actions(db) == []


def test_holidays_add_list_and_soft_delete(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    api = api_as(client, db, clock, settings, make_user(db, it, role=Role.SUPER_ADMIN))
    added = api.add({"date": "2026-11-09", "name": "  Diwali  "})
    assert added.status_code == 201, added.text
    assert added.json()["holidays"] == [{"date": "2026-11-09", "name": "Diwali"}]
    assert added.json()["updated_at"] == "2026-10-27T04:30:00Z"
    db.commit()
    duplicate = api.add({"date": "2026-11-09", "name": "Another"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"
    earlier = api.add({"date": "2026-10-02", "name": "Gandhi Jayanti"})
    assert [holiday["date"] for holiday in earlier.json()["holidays"]] == [
        "2026-10-02",
        "2026-11-09",
    ]
    db.commit()
    assert api.remove("2026-11-09").status_code == 204
    assert api.get().json()["holidays"] == [{"date": "2026-10-02", "name": "Gandhi Jayanti"}]
    for missing in ("2026-11-09", "2026-12-25", "not-a-date", "2026-02-30"):
        response = api.remove(missing)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    assert api.add({"date": "2026-11-09", "name": "Diwali"}).status_code == 201
    stored = db.scalars(select(Holiday).order_by(Holiday.created_at, Holiday.name)).all()
    assert len(stored) == 3
    assert sum(holiday.removed_at is not None for holiday in stored) == 1
    assert actions(db) == ["holiday_added", "holiday_added", "holiday_added", "holiday_removed"]
    removed = db.scalars(select(AuditLog).where(AuditLog.action == "holiday_removed")).one()
    assert removed.object_id == "2026-11-09"
    assert removed.old_value == {"date": "2026-11-09", "name": "Diwali"}


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"date": "2026-13-01", "name": "Bad month"}, "date"),
        ({"date": "09-11-2026", "name": "Wrong order"}, "date"),
        ({"date": "2026-11-09", "name": "x"}, "name"),
        ({"date": "2026-11-09", "name": "y" * 81}, "name"),
        ({"name": "No date"}, "date"),
    ],
)
def test_holiday_validation(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    body: dict[str, object],
    field: str,
) -> None:
    api = api_as(client, db, clock, settings, make_user(db, it, role=Role.SUPER_ADMIN))
    response = api.add(body)
    assert response.status_code == 422, response.text
    assert field in response.json()["error"]["fields"]
