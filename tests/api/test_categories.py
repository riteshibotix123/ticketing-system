import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import Role
from app.core.security import create_access_token
from app.models import AuditLog, Category, Department, PolicyVersion, User
from tests.factories import (
    make_category,
    make_department,
    make_policy_version,
    make_spoke_assignment,
    make_user,
)

CATEGORIES = "/api/v1/categories"


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def disable_admin_management(db: Session) -> None:
    current = db.scalars(select(PolicyVersion).order_by(PolicyVersion.version.desc())).first()
    assert current is not None
    config = dict(current.config)
    config["admins_can_manage_departments"] = False
    make_policy_version(db, current.version + 1, config)


def test_create_category(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    headers = bearer(db, admin, clock, settings)
    url = "/api/v1/departments/IT/categories"
    response = client.post(url, json={"name": "Laptops", "confidential": True}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "department_id", "name", "confidential", "active", "sla_mode"}
    assert body["department_id"] == "IT"
    assert body["confidential"] is True
    assert body["active"] is True
    duplicate = client.post(url, json={"name": "LAPTOPS", "confidential": False}, headers=headers)
    assert duplicate.status_code == 409
    other = make_department(db, "HR")
    db.commit()
    same_name = client.post(
        f"/api/v1/departments/{other.id}/categories", json={"name": "Laptops"}, headers=headers
    )
    assert same_name.status_code == 200
    assert same_name.json()["confidential"] is False
    for name in ("A", "x" * 81):
        bad = client.post(url, json={"name": name}, headers=headers)
        assert bad.status_code == 422
    missing = client.post(
        "/api/v1/departments/ZZ/categories", json={"name": "Desk"}, headers=headers
    )
    assert missing.status_code == 404
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "category_created")).first()
    assert entry is not None
    assert entry.department_id == "IT"


@pytest.mark.parametrize(
    ("kind", "toggle", "expected"),
    [
        ("employee", True, 403),
        ("spoke", True, 403),
        ("admin", True, 200),
        ("admin", False, 403),
        ("super_admin", False, 200),
    ],
)
def test_category_authority(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    kind: str,
    toggle: bool,
    expected: int,
) -> None:
    category = make_category(db, it, "Laptops")
    if not toggle:
        disable_admin_management(db)
    actor = make_user(db, it, role=Role.EMPLOYEE if kind == "spoke" else Role(kind))
    if kind == "spoke":
        make_spoke_assignment(db, actor, it)
    headers = bearer(db, actor, clock, settings)
    created = client.post(
        "/api/v1/departments/IT/categories", json={"name": "Phones"}, headers=headers
    )
    assert created.status_code == expected
    patched = client.patch(f"{CATEGORIES}/{category.id}", json={"name": "Desks"}, headers=headers)
    assert patched.status_code == expected
    deleted = client.delete(f"{CATEGORIES}/{category.id}", headers=headers)
    assert deleted.status_code == (204 if expected == 200 else 403)


def test_update_and_soft_delete(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    category = make_category(db, it, "Laptops")
    make_category(db, it, "Phones")
    admin = make_user(db, it, role=Role.ADMIN)
    headers = bearer(db, admin, clock, settings)
    url = f"{CATEGORIES}/{category.id}"

    response = client.patch(url, json={"name": "Hardware", "confidential": True}, headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Hardware"
    assert response.json()["confidential"] is True
    assert client.patch(url, json={"name": "phones"}, headers=headers).status_code == 409
    assert client.patch(url, json={"name": "HARDWARE"}, headers=headers).status_code == 200

    deleted = client.delete(url, headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    db.expire_all()
    stored = db.get(Category, category.id)
    assert stored is not None
    assert stored.is_active is False
    assert client.delete(url, headers=headers).status_code == 204
    reactivated = client.patch(url, json={"active": True}, headers=headers)
    assert reactivated.json()["active"] is True
    for missing in (f"{CATEGORIES}/nope", f"{CATEGORIES}/00000000-0000-0000-0000-000000000000"):
        assert client.patch(missing, json={"name": "Desk"}, headers=headers).status_code == 404
        assert client.delete(missing, headers=headers).status_code == 404
    actions = sorted(
        db.scalars(select(AuditLog.action).where(AuditLog.object_id == str(category.id)))
    )
    assert actions == [
        "category_deactivated",
        "category_updated",
        "category_updated",
        "category_updated",
    ]


def test_category_sla_basis_override(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    category = make_category(db, it, "Laptops")
    admin = make_user(db, it, role=Role.ADMIN)
    headers = bearer(db, admin, clock, settings)
    url = f"{CATEGORIES}/{category.id}"

    response = client.patch(url, json={"sla_mode": "calendar"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["sla_mode"] == "calendar"
    assert client.patch(url, json={"name": "Hardware"}, headers=headers).json()["sla_mode"] == (
        "calendar"
    )
    assert client.patch(url, json={"sla_mode": None}, headers=headers).json()["sla_mode"] is None
    assert client.patch(url, json={"sla_mode": "hourly"}, headers=headers).status_code == 422
    changes = list(
        db.scalars(
            select(AuditLog.new_value).where(
                AuditLog.action == "sla_basis_changed",
                AuditLog.object_id == str(category.id),
            )
        )
    )
    assert sorted(str(value) for value in changes) == [
        "{'sla_mode': 'calendar'}",
        "{'sla_mode': None}",
    ]
