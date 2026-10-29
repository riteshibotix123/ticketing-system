import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Role
from app.core.events import ConfidentialGrantChanged, bus
from app.core.security import create_access_token
from app.models import AuditLog, Category, ConfidentialGrant, Department, User
from tests.factories import (
    make_category,
    make_confidential_grant,
    make_department,
    make_user,
)

GRANTS = "/api/v1/confidential-grants"


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


@pytest.fixture
def secret(db: Session, it: Department) -> Category:
    return make_category(db, it, "Investigations", is_confidential=True)


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.ADMIN])
def test_only_super_admin_manages_grants(
    client: TestClient,
    db: Session,
    it: Department,
    secret: Category,
    clock: FrozenClock,
    settings: Settings,
    role: Role,
) -> None:
    user = make_user(db, it)
    grant = make_confidential_grant(db, user, secret)
    headers = bearer(db, make_user(db, it, role=role), clock, settings)
    assert client.get(GRANTS, headers=headers).status_code == 403
    created = client.post(
        GRANTS, json={"user_id": str(user.id), "category_id": str(secret.id)}, headers=headers
    )
    assert created.status_code == 403
    assert client.delete(f"{GRANTS}/{grant.id}", headers=headers).status_code == 403


def test_grant_lifecycle(
    client: TestClient,
    db: Session,
    it: Department,
    secret: Category,
    clock: FrozenClock,
    settings: Settings,
) -> None:
    published: list[ConfidentialGrantChanged] = []
    bus.register(ConfidentialGrantChanged, lambda _session, event: published.append(event))
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN, name="Sue Super")
    user = make_user(db, it, name="Gita Grantee")
    headers = bearer(db, super_admin, clock, settings)
    payload = {"user_id": str(user.id), "category_id": str(secret.id)}

    created = client.post(GRANTS, json=payload, headers=headers)
    assert created.status_code == 200
    body = created.json()
    assert set(body) == {"id", "user", "category", "granted_by", "granted_at"}
    assert body["user"]["id"] == str(user.id)
    assert body["category"]["id"] == str(secret.id)
    assert body["category"]["confidential"] is True
    assert body["granted_by"]["id"] == str(super_admin.id)
    assert body["granted_at"] == "2026-10-27T04:30:00Z"
    assert client.post(GRANTS, json=payload, headers=headers).status_code == 409

    listed = client.get(GRANTS, headers=headers).json()
    assert [item["id"] for item in listed] == [body["id"]]
    by_user = client.get(GRANTS, params={"user_id": str(super_admin.id)}, headers=headers)
    assert by_user.json() == []
    by_category = client.get(GRANTS, params={"category_id": str(secret.id)}, headers=headers)
    assert len(by_category.json()) == 1
    assert client.get(GRANTS, params={"user_id": "nope"}, headers=headers).status_code == 422

    revoked = client.delete(f"{GRANTS}/{body['id']}", headers=headers)
    assert revoked.status_code == 204
    db.expire_all()
    grant = db.scalars(select(ConfidentialGrant)).one()
    assert grant.revoked_at == clock.now()
    assert grant.revoked_by_id == super_admin.id
    assert client.get(GRANTS, headers=headers).json() == []
    assert client.delete(f"{GRANTS}/{body['id']}", headers=headers).status_code == 404
    assert client.delete(f"{GRANTS}/nope", headers=headers).status_code == 404
    again = client.post(GRANTS, json=payload, headers=headers)
    assert again.status_code == 200

    entries = db.scalars(select(AuditLog).where(AuditLog.object_type == "confidential_grant")).all()
    assert sorted(entry.action for entry in entries) == [
        "confidential_grant_added",
        "confidential_grant_added",
        "confidential_grant_revoked",
    ]
    assert all(entry.is_security_limited for entry in entries)
    assert [(event.user_id, event.category_id) for event in published] == [(user.id, secret.id)] * 3


def test_create_validation(
    client: TestClient,
    db: Session,
    it: Department,
    secret: Category,
    clock: FrozenClock,
    settings: Settings,
) -> None:
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    user = make_user(db, it)
    gone = make_user(db, it, state=AccountState.DEACTIVATED)
    public = make_category(db, it, "Laptops")
    retired = make_category(db, it, "Old", is_confidential=True, is_active=False)
    headers = bearer(db, super_admin, clock, settings)
    for category in (public, retired):
        response = client.post(
            GRANTS,
            json={"user_id": str(user.id), "category_id": str(category.id)},
            headers=headers,
        )
        assert response.status_code == 422
        assert "category_id" in response.json()["error"]["fields"]
    for user_id in (str(gone.id), "nope"):
        response = client.post(
            GRANTS, json={"user_id": user_id, "category_id": str(secret.id)}, headers=headers
        )
        assert response.status_code == 422
        assert "user_id" in response.json()["error"]["fields"]
