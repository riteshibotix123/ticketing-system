import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import Role
from app.core.security import create_access_token
from app.core.types import JsonObject, JsonValue
from app.models import AuditLog, Department, PolicyVersion, User
from app.services.policy import PolicyService
from tests.factories import make_department, make_spoke_assignment, make_user

POLICY = "/api/v1/policy"
DEFAULT_POLICY: JsonObject = {
    "initial_response_hours": 24,
    "warning_hours": {"low": 18, "medium": 18, "high": 18, "critical": 12},
    "l3_hours": {"low": 48, "medium": 48, "high": 36, "critical": 30},
    "update_warning_hours": 20,
    "update_cadence_hours": 24,
    "eta_warning_hours": 2,
    "escalation_repeat_hours": 24,
    "requester_reminder_hours": 48,
    "auto_close_business_days": 3,
    "reopen_window_days": 7,
    "max_reopens": 3,
    "sla_mode": "calendar",
    "admins_can_manage_departments": True,
}


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def with_changes(**changes: JsonValue) -> JsonObject:
    return {**DEFAULT_POLICY, **changes}


@pytest.mark.parametrize(
    ("kind", "read", "write"),
    [
        ("employee", 403, 403),
        ("spoke", 403, 403),
        ("admin", 200, 403),
        ("super_admin", 200, 200),
    ],
)
def test_policy_authority(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    kind: str,
    read: int,
    write: int,
) -> None:
    actor = make_user(db, it, role=Role.EMPLOYEE if kind == "spoke" else Role(kind))
    if kind == "spoke":
        make_spoke_assignment(db, actor, it)
    headers = bearer(db, actor, clock, settings)
    response = client.get(POLICY, headers=headers)
    assert response.status_code == read
    if read == 200:
        assert response.json() == DEFAULT_POLICY
    assert client.put(POLICY, json=DEFAULT_POLICY, headers=headers).status_code == write


def test_put_creates_new_version(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    headers = bearer(db, super_admin, clock, settings)
    changed = with_changes(max_reopens=5, auto_close_business_days=None)

    response = client.put(POLICY, json=changed, headers=headers)
    assert response.status_code == 200
    assert response.json() == changed
    versions = db.scalars(select(PolicyVersion).order_by(PolicyVersion.version)).all()
    assert [version.version for version in versions] == [1, 2]
    assert versions[0].config["max_reopens"] == 3
    assert versions[1].config == changed
    assert versions[1].created_by_id == super_admin.id
    assert PolicyService(db).current().max_reopens == 5
    assert client.get(POLICY, headers=headers).json() == changed
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "policy_updated")).one()
    assert isinstance(entry.old_value, dict)
    assert isinstance(entry.new_value, dict)
    assert entry.old_value["max_reopens"] == 3
    assert entry.new_value["max_reopens"] == 5
    third = client.put(POLICY, json=DEFAULT_POLICY, headers=headers)
    assert third.status_code == 200
    assert PolicyService(db).current_version().version == 3


def test_admin_toggle_takes_effect(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    admin = make_user(db, it, role=Role.ADMIN)
    response = client.put(
        POLICY,
        json=with_changes(admins_can_manage_departments=False),
        headers=bearer(db, super_admin, clock, settings),
    )
    assert response.status_code == 200
    blocked = client.post(
        "/api/v1/departments",
        json={"id": "FIN", "name": "Finance"},
        headers=bearer(db, admin, clock, settings),
    )
    assert blocked.status_code == 403


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"initial_response_hours": 0}, "initial_response_hours"),
        ({"initial_response_hours": 169}, "initial_response_hours"),
        ({"update_cadence_hours": 200}, "update_cadence_hours"),
        ({"escalation_repeat_hours": 0}, "escalation_repeat_hours"),
        ({"requester_reminder_hours": 169}, "requester_reminder_hours"),
        ({"eta_warning_hours": 49}, "eta_warning_hours"),
        ({"eta_warning_hours": 0}, "eta_warning_hours"),
        ({"auto_close_business_days": 0}, "auto_close_business_days"),
        ({"auto_close_business_days": 31}, "auto_close_business_days"),
        ({"reopen_window_days": 91}, "reopen_window_days"),
        ({"reopen_window_days": 0}, "reopen_window_days"),
        ({"max_reopens": -1}, "max_reopens"),
        ({"max_reopens": 11}, "max_reopens"),
        ({"sla_mode": "weekly"}, "sla_mode"),
        ({"warning_hours": {"low": 18, "medium": 18, "high": 18}}, "warning_hours"),
        (
            {"warning_hours": {"low": 24, "medium": 18, "high": 18, "critical": 12}},
            "warning_hours",
        ),
        ({"l3_hours": {"low": 48, "medium": 48, "high": 36}}, "l3_hours"),
        ({"l3_hours": {"low": 48, "medium": 24, "high": 36, "critical": 30}}, "l3_hours"),
        ({"update_warning_hours": 24}, "update_warning_hours"),
        ({"warning_hours": {"low": 0, "medium": 18, "high": 18, "critical": 12}}, "low"),
        ({"admins_can_manage_departments": None}, "admins_can_manage_departments"),
    ],
)
def test_put_validation(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    changes: JsonObject,
    field: str,
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    response = client.put(
        POLICY, json=with_changes(**changes), headers=bearer(db, super_admin, clock, settings)
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in error["fields"]
    assert PolicyService(db).current_version().version == 1


def test_put_requires_every_field(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    incomplete = {key: value for key, value in DEFAULT_POLICY.items() if key != "max_reopens"}
    response = client.put(POLICY, json=incomplete, headers=bearer(db, super_admin, clock, settings))
    assert response.status_code == 422
    assert "max_reopens" in response.json()["error"]["fields"]


def test_put_accepts_business_mode(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    response = client.put(
        POLICY,
        json=with_changes(sla_mode="business"),
        headers=bearer(db, super_admin, clock, settings),
    )
    assert response.status_code == 200, response.text
    assert response.json()["sla_mode"] == "business"
    assert PolicyService(db).current().sla_mode == "business"
