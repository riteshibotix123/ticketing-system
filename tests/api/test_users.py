import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, ProtectedActionKind, Role, TicketStatus
from app.core.events import UserDeactivated, bus
from app.core.security import create_access_token
from app.models import (
    AuditLog,
    Department,
    PolicyVersion,
    ProtectedActionRequest,
    RefreshToken,
    SpokeAssignment,
    User,
)
from tests.factories import (
    make_department,
    make_policy_version,
    make_refresh_token,
    make_spoke_assignment,
    make_ticket,
    make_user,
)

USERS = "/api/v1/users"
USER_REF_KEYS = {"id", "name", "email"}
USER_LIST_ITEM_KEYS = USER_REF_KEYS | {
    "roles",
    "state",
    "department_id",
    "spoke_departments",
    "last_login_at",
    "created_at",
}
REASON = "Left the company"


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


@pytest.fixture
def hr(db: Session) -> Department:
    return make_department(db, "HR", "Human Resources")


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


def audit_actions(db: Session, user: User) -> list[str]:
    statement = (
        select(AuditLog.action)
        .where(AuditLog.object_id == str(user.id))
        .order_by(AuditLog.created_at, AuditLog.action)
    )
    return list(db.scalars(statement))


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
def test_list_users_permission(
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
    response = client.get(USERS, headers=bearer(db, actor, clock, settings))
    assert response.status_code == expected


def test_list_users_shape_and_filters(
    client: TestClient,
    db: Session,
    it: Department,
    hr: Department,
    clock: FrozenClock,
    settings: Settings,
) -> None:
    admin = make_user(db, it, role=Role.ADMIN, name="Alice Admin")
    spoke = make_user(db, it, name="Bob Spoke", email="bob@ibotix.ai")
    make_spoke_assignment(db, spoke, hr)
    make_user(db, hr, name="Carol HR")
    make_user(db, it, name="Dave Pending", state=AccountState.PENDING_VERIFICATION)
    make_user(db, it, name="Erin Gone", state=AccountState.DEACTIVATED)
    headers = bearer(db, admin, clock, settings)

    body = client.get(USERS, headers=headers).json()
    names = [item["name"] for item in body["items"]]
    assert names == ["Alice Admin", "Bob Spoke", "Carol HR", "Erin Gone"]
    assert body["total"] == 4
    assert body["page"] == 1
    assert body["page_size"] == 25
    item = body["items"][1]
    assert set(item) == USER_LIST_ITEM_KEYS
    assert item["roles"] == ["employee", "spoke"]
    assert item["spoke_departments"] == ["HR"]
    assert item["department_id"] == "IT"
    assert item["last_login_at"] is None
    assert body["items"][0]["roles"] == ["employee", "admin"]

    def names_for(params: dict[str, str]) -> list[str]:
        response = client.get(USERS, params=params, headers=headers)
        assert response.status_code == 200
        return [entry["name"] for entry in response.json()["items"]]

    assert names_for({"q": "BOB@"}) == ["Bob Spoke"]
    assert names_for({"q": "carol"}) == ["Carol HR"]
    assert names_for({"role": "spoke"}) == ["Bob Spoke"]
    assert names_for({"role": "admin"}) == ["Alice Admin"]
    assert names_for({"state": "deactivated"}) == ["Erin Gone"]
    assert names_for({"state": "pending_verification"}) == []
    assert names_for({"department_id": "HR"}) == ["Bob Spoke", "Carol HR"]
    assert names_for({"q": "%"}) == []
    bad = client.get(USERS, params={"role": "resolver"}, headers=headers)
    assert bad.status_code == 422


def test_lookup_returns_active_user_refs(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    caller = make_user(db, it, name="Zed Caller")
    make_user(db, it, name="Priya Active", title="Engineer")
    make_user(db, it, name="Priya Gone", state=AccountState.DEACTIVATED)
    make_user(db, it, name="Priya Waiting", state=AccountState.PENDING_APPROVAL)
    for index in range(25):
        make_user(db, it, name=f"Many {index:02d}")
    headers = bearer(db, caller, clock, settings)

    response = client.get(f"{USERS}/lookup", params={"q": "priya"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [entry["name"] for entry in body] == ["Priya Active"]
    assert set(body[0]) == USER_REF_KEYS | {"title"}
    assert body[0]["title"] == "Engineer"
    many = client.get(f"{USERS}/lookup", params={"q": "many"}, headers=headers).json()
    assert len(many) == 20
    for query in ({"q": "p"}, {"q": " p "}, {}):
        short = client.get(f"{USERS}/lookup", params=query, headers=headers)
        assert short.status_code == 422
        assert error_code(short) == "validation_error"
        assert "q" in short.json()["error"]["fields"]
    assert client.get(f"{USERS}/lookup", params={"q": "priya"}).status_code == 401


def test_department_members(
    client: TestClient,
    db: Session,
    it: Department,
    hr: Department,
    clock: FrozenClock,
    settings: Settings,
) -> None:
    caller = make_user(db, hr, name="Caller")
    make_user(db, it, name="Home Member")
    mapped = make_user(db, hr, name="Mapped Spoke")
    make_spoke_assignment(db, mapped, it)
    revoked = make_user(db, hr, name="Revoked Spoke")
    make_spoke_assignment(db, revoked, it, revoked_at=clock.now())
    make_user(db, it, name="Inactive Member", state=AccountState.DEACTIVATED)
    headers = bearer(db, caller, clock, settings)

    response = client.get("/api/v1/departments/IT/members", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [entry["name"] for entry in body] == ["Home Member", "Mapped Spoke"]
    assert all(set(entry) == USER_REF_KEYS for entry in body)
    missing = client.get("/api/v1/departments/ZZ/members", headers=headers)
    assert missing.status_code == 404
    assert error_code(missing) == "not_found"


def test_update_roles_replaces_mappings(
    client: TestClient,
    db: Session,
    it: Department,
    hr: Department,
    clock: FrozenClock,
    settings: Settings,
) -> None:
    make_department(db, "FIN", "Finance")
    admin = make_user(db, it, role=Role.ADMIN)
    target = make_user(db, it)
    make_spoke_assignment(db, target, it)
    make_spoke_assignment(db, target, hr)
    headers = bearer(db, admin, clock, settings)

    response = client.patch(
        f"{USERS}/{target.id}/roles",
        json={"spoke_departments": ["HR", "FIN"], "reason": "Moved to finance desk"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == USER_LIST_ITEM_KEYS
    assert body["spoke_departments"] == ["FIN", "HR"]
    assert body["roles"] == ["employee", "spoke"]
    mappings = db.scalars(select(SpokeAssignment).where(SpokeAssignment.user_id == target.id))
    by_department = {row.department_id: row for row in mappings}
    assert by_department["IT"].revoked_at == clock.now()
    assert by_department["IT"].revoked_by_id == admin.id
    assert by_department["FIN"].granted_by_id == admin.id
    assert by_department["HR"].revoked_at is None
    entries = db.scalars(select(AuditLog).where(AuditLog.object_id == str(target.id))).all()
    assert sorted((entry.action, entry.department_id) for entry in entries) == [
        ("spoke_mapping_added", "FIN"),
        ("spoke_mapping_revoked", "IT"),
    ]
    assert all(entry.reason == "Moved to finance desk" for entry in entries)

    cleared = client.patch(
        f"{USERS}/{target.id}/roles",
        json={"spoke_departments": [], "reason": "No longer a Spoke"},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["roles"] == ["employee"]


def test_update_roles_validation_and_authority(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    other_admin = make_user(db, it, role=Role.ADMIN)
    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    employee = make_user(db, it)
    gone = make_user(db, it, state=AccountState.DEACTIVATED)
    headers = bearer(db, admin, clock, settings)
    body = {"spoke_departments": ["IT"], "reason": "Covering the desk"}

    for target in (other_admin, super_admin):
        response = client.patch(f"{USERS}/{target.id}/roles", json=body, headers=headers)
        assert response.status_code == 403
    deactivated = client.patch(f"{USERS}/{gone.id}/roles", json=body, headers=headers)
    assert deactivated.status_code == 409
    unknown = client.patch(
        f"{USERS}/{employee.id}/roles",
        json={"spoke_departments": ["ZZ"], "reason": "Covering the desk"},
        headers=headers,
    )
    assert unknown.status_code == 422
    assert "spoke_departments" in unknown.json()["error"]["fields"]
    short = client.patch(
        f"{USERS}/{employee.id}/roles",
        json={"spoke_departments": ["IT"], "reason": "abc"},
        headers=headers,
    )
    assert short.status_code == 422
    assert "reason" in short.json()["error"]["fields"]
    missing = client.patch(f"{USERS}/not-a-uuid/roles", json=body, headers=headers)
    assert missing.status_code == 404
    as_employee = client.patch(
        f"{USERS}/{employee.id}/roles", json=body, headers=bearer(db, employee, clock, settings)
    )
    assert as_employee.status_code == 403
    super_headers = bearer(db, super_admin, clock, settings)
    allowed = client.patch(f"{USERS}/{other_admin.id}/roles", json=body, headers=super_headers)
    assert allowed.status_code == 200
    disable_admin_management(db)
    toggled = client.patch(
        f"{USERS}/{employee.id}/roles", json=body, headers=bearer(db, admin, clock, settings)
    )
    assert toggled.status_code == 403


@pytest.mark.parametrize(
    ("actor_kind", "target_role", "expected"),
    [
        ("employee", Role.EMPLOYEE, 403),
        ("spoke", Role.EMPLOYEE, 403),
        ("admin", Role.EMPLOYEE, 200),
        ("admin", Role.ADMIN, 403),
        ("admin", Role.SUPER_ADMIN, 403),
        ("super_admin", Role.EMPLOYEE, 200),
        ("super_admin", Role.ADMIN, 200),
    ],
)
def test_deactivate_permission_matrix(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    actor_kind: str,
    target_role: Role,
    expected: int,
) -> None:
    actor = make_actor(db, it, actor_kind)
    target = make_user(db, it, role=target_role)
    response = client.post(
        f"{USERS}/{target.id}/deactivate",
        json={"reason": REASON},
        headers=bearer(db, actor, clock, settings),
    )
    assert response.status_code == expected
    db.refresh(target)
    expected_state = AccountState.DEACTIVATED if expected == 200 else AccountState.ACTIVE
    assert target.state is expected_state


def test_admin_can_deactivate_spoke_and_not_while_toggle_off(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    spoke = make_actor(db, it, "spoke")
    other = make_user(db, it)
    headers = bearer(db, admin, clock, settings)
    response = client.post(
        f"{USERS}/{spoke.id}/deactivate", json={"reason": REASON}, headers=headers
    )
    assert response.status_code == 200
    disable_admin_management(db)
    blocked = client.post(
        f"{USERS}/{other.id}/deactivate",
        json={"reason": REASON},
        headers=bearer(db, admin, clock, settings),
    )
    assert blocked.status_code == 403


def test_deactivation_effects(
    client: TestClient,
    db: Session,
    it: Department,
    hr: Department,
    clock: FrozenClock,
    settings: Settings,
) -> None:
    published: list[UserDeactivated] = []
    bus.register(UserDeactivated, lambda _session, event: published.append(event))
    admin = make_user(db, it, role=Role.ADMIN)
    target = make_user(db, it)
    make_spoke_assignment(db, target, it)
    make_spoke_assignment(db, target, hr)
    it.escalation_contact_user_id = target.id
    hr.escalation_contact_user_id = target.id
    token = make_refresh_token(db, target)
    requester = make_user(db, hr)
    make_ticket(db, requester, it, status=TicketStatus.IN_PROGRESS, owner=target)
    make_ticket(db, requester, it, status=TicketStatus.ON_HOLD, assignee=target)
    make_ticket(db, requester, it, status=TicketStatus.ASSIGNED, owner=target, assignee=target)
    make_ticket(db, requester, it, status=TicketStatus.RESOLVED, owner=target)
    make_ticket(db, requester, it, status=TicketStatus.CLOSED, owner=target)
    make_ticket(db, requester, it, status=TicketStatus.IN_PROGRESS)
    target_headers = bearer(db, target, clock, settings)

    response = client.post(
        f"{USERS}/{target.id}/deactivate",
        json={"reason": REASON},
        headers=bearer(db, admin, clock, settings),
    )
    assert response.status_code == 200
    assert response.json() == {
        "result": "deactivated",
        "open_ticket_count": 3,
        "protected_action_id": None,
    }
    db.expire_all()
    user = db.get(User, target.id)
    assert user is not None
    assert user.state is AccountState.DEACTIVATED
    assert user.deactivated_by_id == admin.id
    assert user.deactivated_at == clock.now()
    assert user.deactivation_reason == REASON
    refreshed = db.get(RefreshToken, token.id)
    assert refreshed is not None
    assert refreshed.revoked_at == clock.now()
    active = db.scalars(
        select(SpokeAssignment).where(
            SpokeAssignment.user_id == target.id, SpokeAssignment.revoked_at.is_(None)
        )
    ).all()
    assert active == []
    for department_id in ("IT", "HR"):
        department = db.get(Department, department_id)
        assert department is not None
        assert department.escalation_contact_user_id is None
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "user_deactivated")).one()
    assert entry.actor_id == admin.id
    assert entry.reason == REASON
    assert entry.new_value == {
        "state": "deactivated",
        "open_ticket_count": 3,
        "cleared_escalation_departments": ["HR", "IT"],
    }
    assert [(event.user_id, event.open_ticket_count) for event in published] == [(target.id, 3)]
    assert client.get("/api/v1/auth/me", headers=target_headers).status_code == 401
    again = client.post(
        f"{USERS}/{target.id}/deactivate",
        json={"reason": REASON},
        headers=bearer(db, admin, clock, settings),
    )
    assert again.status_code == 409


@pytest.mark.parametrize("role", [Role.ADMIN, Role.SUPER_ADMIN])
def test_self_deactivation_refused(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    role: Role,
) -> None:
    actor = make_user(db, it, role=role)
    for _ in range(3):
        make_user(db, it, role=Role.SUPER_ADMIN)
    response = client.post(
        f"{USERS}/{actor.id}/deactivate",
        json={"reason": REASON},
        headers=bearer(db, actor, clock, settings),
    )
    assert response.status_code == 403
    db.refresh(actor)
    assert actor.state is AccountState.ACTIVE
    assert db.scalars(select(ProtectedActionRequest)).all() == []


def test_deactivate_requires_reason(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    target = make_user(db, it)
    headers = bearer(db, admin, clock, settings)
    for body in ({}, {"reason": "    no "}, {"reason": "x" * 1001}):
        response = client.post(f"{USERS}/{target.id}/deactivate", json=body, headers=headers)
        assert response.status_code == 422
        assert "reason" in response.json()["error"]["fields"]
    missing = client.post(
        f"{USERS}/00000000-0000-0000-0000-000000000000/deactivate",
        json={"reason": REASON},
        headers=headers,
    )
    assert missing.status_code == 404


def test_super_admin_target_creates_protected_action(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester = make_user(db, it, role=Role.SUPER_ADMIN)
    target = make_user(db, it, role=Role.SUPER_ADMIN)
    make_user(db, it, role=Role.SUPER_ADMIN)
    owner_of = make_user(db, it)
    make_ticket(db, owner_of, it, status=TicketStatus.IN_PROGRESS, owner=target)
    response = client.post(
        f"{USERS}/{target.id}/deactivate",
        json={"reason": REASON},
        headers=bearer(db, requester, clock, settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "protected_request_created"
    assert body["open_ticket_count"] == 1
    request = db.scalars(select(ProtectedActionRequest)).one()
    assert body["protected_action_id"] == str(request.id)
    assert request.kind is ProtectedActionKind.DEACTIVATE_SUPER_ADMIN
    assert request.reason == REASON
    db.refresh(target)
    assert target.state is AccountState.ACTIVE


def test_super_admin_target_blocked_at_two(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester = make_user(db, it, role=Role.SUPER_ADMIN)
    target = make_user(db, it, role=Role.SUPER_ADMIN)
    response = client.post(
        f"{USERS}/{target.id}/deactivate",
        json={"reason": REASON},
        headers=bearer(db, requester, clock, settings),
    )
    assert response.status_code == 409
    assert error_code(response) == "protected_action_blocked"


def test_activate(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    target = make_user(db, it)
    active = make_user(db, it)
    never_approved = make_user(db, it, state=AccountState.DEACTIVATED)
    never_approved.approved_at = None
    deactivated_admin = make_user(db, it, role=Role.ADMIN)
    headers = bearer(db, admin, clock, settings)
    deactivate = client.post(
        f"{USERS}/{target.id}/deactivate", json={"reason": REASON}, headers=headers
    )
    assert deactivate.status_code == 200

    response = client.post(f"{USERS}/{target.id}/activate", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == USER_LIST_ITEM_KEYS
    assert body["state"] == "active"
    db.refresh(target)
    assert target.deactivated_at is None
    assert audit_actions(db, target) == ["user_activated", "user_deactivated"]
    assert client.post(f"{USERS}/{active.id}/activate", headers=headers).status_code == 409
    assert client.post(f"{USERS}/{never_approved.id}/activate", headers=headers).status_code == 409
    deactivated_admin.state = AccountState.DEACTIVATED
    blocked = client.post(
        f"{USERS}/{deactivated_admin.id}/activate", headers=bearer(db, admin, clock, settings)
    )
    assert blocked.status_code == 403
