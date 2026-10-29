import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Role
from app.core.security import create_access_token
from app.models import AuditLog, Department, PolicyVersion, SpokeAssignment, User
from tests.factories import (
    make_category,
    make_department,
    make_policy_version,
    make_spoke_assignment,
    make_user,
)

DEPARTMENTS = "/api/v1/departments"
DEPARTMENT_KEYS = {
    "id",
    "name",
    "active",
    "accepts_tickets",
    "spokes",
    "escalation_contact",
    "categories",
    "sla_mode",
}
CATEGORY_KEYS = {"id", "department_id", "name", "confidential", "active", "sla_mode"}


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


def disable_admin_management(db: Session) -> None:
    current = db.scalars(select(PolicyVersion).order_by(PolicyVersion.version.desc())).first()
    assert current is not None
    config = dict(current.config)
    config["admins_can_manage_departments"] = False
    make_policy_version(db, current.version + 1, config)


def make_actor(db: Session, department: Department, kind: str) -> User:
    if kind == "spoke":
        user = make_user(db, department)
        make_spoke_assignment(db, user, department)
        return user
    return make_user(db, department, role=Role(kind))


def test_list_shape_and_accepts_tickets(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    hr = make_department(db, "HR", "Human Resources")
    make_department(db, "OPS", "Operations", is_active=False)
    spoke = make_user(db, it, name="Sam Spoke")
    make_spoke_assignment(db, spoke, it)
    gone = make_user(db, hr, name="Gone Spoke", state=AccountState.DEACTIVATED)
    make_spoke_assignment(db, gone, hr)
    it.escalation_contact_user_id = spoke.id
    make_category(db, it, "Laptops")
    make_category(db, it, "Access", is_confidential=True, is_active=False)
    employee = make_user(db, it)

    response = client.get(DEPARTMENTS, headers=bearer(db, employee, clock, settings))
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == ["HR", "IT"]
    by_id = {item["id"]: item for item in body}
    assert set(by_id["IT"]) == DEPARTMENT_KEYS
    assert by_id["IT"]["accepts_tickets"] is True
    assert [spoke_ref["name"] for spoke_ref in by_id["IT"]["spokes"]] == ["Sam Spoke"]
    assert by_id["IT"]["escalation_contact"]["id"] == str(spoke.id)
    assert [category["name"] for category in by_id["IT"]["categories"]] == ["Access", "Laptops"]
    assert set(by_id["IT"]["categories"][0]) == CATEGORY_KEYS
    assert by_id["IT"]["categories"][0]["confidential"] is True
    assert by_id["HR"]["accepts_tickets"] is False
    assert by_id["HR"]["spokes"] == []
    assert by_id["HR"]["escalation_contact"] is None


@pytest.mark.parametrize(
    ("kind", "toggle", "sees_inactive"),
    [
        ("employee", True, False),
        ("spoke", True, False),
        ("admin", True, True),
        ("admin", False, False),
        ("super_admin", False, True),
    ],
)
def test_inactive_departments_only_for_managers(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    kind: str,
    toggle: bool,
    sees_inactive: bool,
) -> None:
    make_department(db, "OPS", "Operations", is_active=False)
    if not toggle:
        disable_admin_management(db)
    actor = make_actor(db, it, kind)
    body = client.get(DEPARTMENTS, headers=bearer(db, actor, clock, settings)).json()
    assert ("OPS" in {item["id"] for item in body}) is sees_inactive


@pytest.mark.parametrize(
    ("kind", "toggle", "expected"),
    [
        ("employee", True, 403),
        ("spoke", True, 403),
        ("admin", True, 200),
        ("admin", False, 403),
        ("super_admin", True, 200),
        ("super_admin", False, 200),
    ],
)
def test_create_authority(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    kind: str,
    toggle: bool,
    expected: int,
) -> None:
    if not toggle:
        disable_admin_management(db)
    actor = make_actor(db, it, kind)
    response = client.post(
        DEPARTMENTS,
        json={"id": "FIN", "name": "Finance"},
        headers=bearer(db, actor, clock, settings),
    )
    assert response.status_code == expected


def test_create_rules(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    headers = bearer(db, admin, clock, settings)
    response = client.post(DEPARTMENTS, json={"id": "FIN", "name": " Finance "}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": "FIN",
        "name": "Finance",
        "active": False,
        "accepts_tickets": False,
        "spokes": [],
        "escalation_contact": None,
        "categories": [],
        "sla_mode": None,
    }
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "department_created")).one()
    assert entry.department_id == "FIN"
    duplicate = client.post(DEPARTMENTS, json={"id": "IT", "name": "Again"}, headers=headers)
    assert duplicate.status_code == 409
    for payload in (
        {"id": "it", "name": "Lower"},
        {"id": "I", "name": "Short"},
        {"id": "TOOLONG", "name": "Long"},
        {"id": "A1", "name": "Digit"},
    ):
        bad = client.post(DEPARTMENTS, json=payload, headers=headers)
        assert bad.status_code == 422
        assert "id" in bad.json()["error"]["fields"]
    for name in ("A", "x" * 81):
        bad = client.post(DEPARTMENTS, json={"id": "OPS", "name": name}, headers=headers)
        assert bad.status_code == 422
        assert "name" in bad.json()["error"]["fields"]


def test_update_and_activation_guard(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings
) -> None:
    fin = make_department(db, "FIN", "Finance", is_active=False)
    admin = make_user(db, fin, role=Role.ADMIN)
    headers = bearer(db, admin, clock, settings)
    url = f"{DEPARTMENTS}/FIN"

    blocked = client.patch(url, json={"active": True}, headers=headers)
    assert blocked.status_code == 409
    gone = make_user(db, fin, state=AccountState.DEACTIVATED)
    make_spoke_assignment(db, gone, fin)
    db.commit()
    assert client.patch(url, json={"active": True}, headers=headers).status_code == 409

    renamed = client.patch(url, json={"name": "Finance and Accounts"}, headers=headers)
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Finance and Accounts"
    spoke = make_user(db, fin)
    make_spoke_assignment(db, spoke, fin)
    db.commit()
    activated = client.patch(url, json={"active": True}, headers=headers)
    assert activated.status_code == 200
    assert activated.json()["active"] is True
    assert activated.json()["accepts_tickets"] is True
    deactivated = client.patch(url, json={"active": False}, headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["accepts_tickets"] is False
    actions = list(
        db.scalars(select(AuditLog.action).where(AuditLog.action == "department_updated"))
    )
    assert len(actions) == 3
    unknown = client.patch(f"{DEPARTMENTS}/ZZ", json={"name": "Nope"}, headers=headers)
    assert unknown.status_code == 404
    assert client.patch(url, json={"id": "NEW"}, headers=headers).status_code == 200
    db.refresh(fin)
    assert fin.id == "FIN"


def test_spoke_add_and_remove(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    user = make_user(db, it, name="New Spoke")
    gone = make_user(db, it, state=AccountState.DEACTIVATED)
    headers = bearer(db, admin, clock, settings)
    url = f"{DEPARTMENTS}/IT/spokes"

    added = client.post(url, json={"user_id": str(user.id)}, headers=headers)
    assert added.status_code == 200
    assert [ref["id"] for ref in added.json()["spokes"]] == [str(user.id)]
    assert added.json()["accepts_tickets"] is True
    duplicate = client.post(url, json={"user_id": str(user.id)}, headers=headers)
    assert duplicate.status_code == 409
    for user_id in (str(gone.id), "not-a-uuid", "00000000-0000-0000-0000-000000000000"):
        bad = client.post(url, json={"user_id": user_id}, headers=headers)
        assert bad.status_code == 422
        assert "user_id" in bad.json()["error"]["fields"]
    assert (
        client.post(f"{DEPARTMENTS}/ZZ/spokes", json={"user_id": str(user.id)}, headers=headers)
    ).status_code == 404

    removed = client.delete(f"{url}/{user.id}", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["spokes"] == []
    assert removed.json()["active"] is True
    assert removed.json()["accepts_tickets"] is False
    assignment = db.scalars(select(SpokeAssignment).where(SpokeAssignment.user_id == user.id)).one()
    assert assignment.revoked_at == clock.now()
    assert assignment.revoked_by_id == admin.id
    assert client.delete(f"{url}/{user.id}", headers=headers).status_code == 404
    actions = sorted(db.scalars(select(AuditLog.action).where(AuditLog.object_id == str(user.id))))
    assert actions == ["spoke_mapping_added", "spoke_mapping_revoked"]


def test_spoke_endpoints_need_department_management(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    user = make_user(db, it)
    disable_admin_management(db)
    headers = bearer(db, admin, clock, settings)
    url = f"{DEPARTMENTS}/IT/spokes"
    assert client.post(url, json={"user_id": str(user.id)}, headers=headers).status_code == 403
    assert client.delete(f"{url}/{user.id}", headers=headers).status_code == 403
    escalation = client.put(
        f"{DEPARTMENTS}/IT/escalation", json={"contact_id": None}, headers=headers
    )
    assert escalation.status_code == 403
    renamed = client.patch(f"{DEPARTMENTS}/IT", json={"name": "IT"}, headers=headers)
    assert renamed.status_code == 403


def test_escalation_contact(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    hr = make_department(db, "HR", "Human Resources")
    admin = make_user(db, hr, role=Role.ADMIN)
    home = make_user(db, it, name="Home Member")
    mapped = make_user(db, hr, name="Mapped Spoke")
    make_spoke_assignment(db, mapped, it)
    outsider = make_user(db, hr)
    gone = make_user(db, it, state=AccountState.DEACTIVATED)
    headers = bearer(db, admin, clock, settings)
    url = f"{DEPARTMENTS}/IT/escalation"

    for user in (home, mapped):
        response = client.put(url, json={"contact_id": str(user.id)}, headers=headers)
        assert response.status_code == 200
        assert response.json()["escalation_contact"]["id"] == str(user.id)
    for user_id in (str(outsider.id), str(gone.id), "nope"):
        bad = client.put(url, json={"contact_id": user_id}, headers=headers)
        assert bad.status_code == 422
        assert "contact_id" in bad.json()["error"]["fields"]
    cleared = client.put(url, json={"contact_id": None}, headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["escalation_contact"] is None
    db.refresh(it)
    assert it.escalation_contact_user_id is None
    entries = db.scalars(
        select(AuditLog).where(AuditLog.action == "escalation_contact_changed")
    ).all()
    assert len(entries) == 3
    assert client.put(url, json={}, headers=headers).status_code == 422


def test_sla_basis_override(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    headers = bearer(db, admin, clock, settings)
    url = f"{DEPARTMENTS}/IT"

    switched = client.patch(url, json={"sla_mode": "business"}, headers=headers)
    assert switched.status_code == 200, switched.text
    assert switched.json()["sla_mode"] == "business"
    renamed = client.patch(url, json={"name": "IT Services"}, headers=headers)
    assert renamed.json()["sla_mode"] == "business"
    inherited = client.patch(url, json={"sla_mode": None}, headers=headers)
    assert inherited.json()["sla_mode"] is None
    assert client.patch(url, json={"sla_mode": None}, headers=headers).status_code == 200
    invalid = client.patch(url, json={"sla_mode": "weekly"}, headers=headers)
    assert invalid.status_code == 422
    assert "sla_mode" in invalid.json()["error"]["fields"]
    entries = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.action == "sla_basis_changed")
            .order_by(AuditLog.created_at, AuditLog.id)
        )
    )
    assert sorted(str((entry.old_value, entry.new_value)) for entry in entries) == sorted(
        [
            str(({"sla_mode": None}, {"sla_mode": "business"})),
            str(({"sla_mode": "business"}, {"sla_mode": None})),
        ]
    )
    assert all(entry.object_id == "IT" and entry.department_id == "IT" for entry in entries)
    employee = make_user(db, it)
    forbidden = client.patch(
        url, json={"sla_mode": "business"}, headers=bearer(db, employee, clock, settings)
    )
    assert forbidden.status_code == 403
