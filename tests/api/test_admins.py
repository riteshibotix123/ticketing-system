import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Role
from app.core.security import create_access_token
from app.models import AuditLog, Department, User
from tests.factories import make_department, make_spoke_assignment, make_user

ADMINS = "/api/v1/admins"


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


@pytest.mark.parametrize("kind", ["employee", "spoke", "admin"])
def test_only_super_admin_manages_admins(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    kind: str,
) -> None:
    actor = make_user(db, it, role=Role.ADMIN if kind == "admin" else Role.EMPLOYEE)
    if kind == "spoke":
        make_spoke_assignment(db, actor, it)
    employee = make_user(db, it)
    admin = make_user(db, it, role=Role.ADMIN)
    headers = bearer(db, actor, clock, settings)
    assert client.get(ADMINS, headers=headers).status_code == 403
    promote = client.post(ADMINS, json={"user_id": str(employee.id)}, headers=headers)
    assert promote.status_code == 403
    demote = client.delete(f"{ADMINS}/{admin.id}", headers=headers)
    assert demote.status_code == 403
    db.refresh(employee)
    db.refresh(admin)
    assert employee.global_role is Role.EMPLOYEE
    assert admin.global_role is Role.ADMIN


def test_list_admins_any_state(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN, name="Ann Super")
    make_user(db, it, role=Role.ADMIN, name="Ben Admin")
    make_user(db, it, role=Role.ADMIN, name="Cat Gone", state=AccountState.DEACTIVATED)
    make_user(db, it, name="Dan Employee")
    response = client.get(ADMINS, headers=bearer(db, super_admin, clock, settings))
    assert response.status_code == 200
    body = response.json()
    assert [(item["name"], item["state"]) for item in body] == [
        ("Ann Super", "active"),
        ("Ben Admin", "active"),
        ("Cat Gone", "deactivated"),
    ]
    assert body[0]["roles"] == ["employee", "super_admin"]


def test_promote_and_demote(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    employee = make_user(db, it)
    make_spoke_assignment(db, employee, it)
    headers = bearer(db, super_admin, clock, settings)

    promoted = client.post(ADMINS, json={"user_id": str(employee.id)}, headers=headers)
    assert promoted.status_code == 200
    assert promoted.json()["roles"] == ["employee", "spoke", "admin"]
    db.refresh(employee)
    assert employee.global_role is Role.ADMIN
    again = client.post(ADMINS, json={"user_id": str(employee.id)}, headers=headers)
    assert again.status_code == 409

    demoted = client.delete(f"{ADMINS}/{employee.id}", headers=headers)
    assert demoted.status_code == 200
    assert demoted.json()["roles"] == ["employee", "spoke"]
    assert db.scalar(select(User.global_role).where(User.id == employee.id)) is Role.EMPLOYEE
    entries = db.scalars(
        select(AuditLog).where(AuditLog.object_id == str(employee.id)).order_by(AuditLog.action)
    ).all()
    assert [(entry.action, entry.is_security_limited) for entry in entries] == [
        ("admin_demoted", True),
        ("admin_promoted", True),
    ]
    not_admin = client.delete(f"{ADMINS}/{employee.id}", headers=headers)
    assert not_admin.status_code == 409
    assert error_code(not_admin) == "conflict"


def test_promote_requires_active_existing_employee(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    gone = make_user(db, it, state=AccountState.DEACTIVATED)
    headers = bearer(db, super_admin, clock, settings)
    inactive = client.post(ADMINS, json={"user_id": str(gone.id)}, headers=headers)
    assert inactive.status_code == 409
    for user_id in ("not-a-uuid", "00000000-0000-0000-0000-000000000000"):
        unknown = client.post(ADMINS, json={"user_id": user_id}, headers=headers)
        assert unknown.status_code == 422
        assert "user_id" in unknown.json()["error"]["fields"]
    self_promote = client.post(ADMINS, json={"user_id": str(super_admin.id)}, headers=headers)
    assert self_promote.status_code == 409


def test_demote_super_admin_is_blocked(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    other = make_user(db, it, role=Role.SUPER_ADMIN)
    response = client.delete(
        f"{ADMINS}/{other.id}", headers=bearer(db, super_admin, clock, settings)
    )
    assert response.status_code == 409
    assert error_code(response) == "protected_action_blocked"
    db.refresh(other)
    assert other.global_role is Role.SUPER_ADMIN
    missing = client.delete(
        f"{ADMINS}/00000000-0000-0000-0000-000000000000",
        headers=bearer(db, super_admin, clock, settings),
    )
    assert missing.status_code == 404
