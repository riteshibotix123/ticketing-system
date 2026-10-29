from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Role, SignupStatus
from app.core.events import SignupDecided, bus
from app.core.security import create_access_token
from app.models import AuditLog, Department, EmailOutbox, SignupRequest, User
from tests.factories import (
    FACTORY_NOW,
    make_department,
    make_signup_request,
    make_spoke_assignment,
    make_user,
)

LIST = "/api/v1/signup-requests"


def approve_url(request: SignupRequest) -> str:
    return f"{LIST}/{request.id}/approve"


def reject_url(request: SignupRequest) -> str:
    return f"{LIST}/{request.id}/reject"


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


def applicant(
    db: Session,
    department: Department,
    *,
    role: Role = Role.EMPLOYEE,
    state: AccountState = AccountState.PENDING_APPROVAL,
    email: str | None = None,
    at_offset: timedelta = timedelta(0),
) -> SignupRequest:
    at = FACTORY_NOW + at_offset
    user = make_user(db, department, email=email, state=state, at=at)
    return make_signup_request(db, user, department, requested_role=role, at=at)


def approver(db: Session, department: Department, kind: str) -> User:
    if kind == "spoke":
        user = make_user(db, department)
        make_spoke_assignment(db, user, department)
        return user
    return make_user(db, department, role=Role(kind))


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


@pytest.mark.parametrize(
    ("approver_kind", "requested", "allowed"),
    [
        ("employee", Role.EMPLOYEE, False),
        ("employee", Role.ADMIN, False),
        ("employee", Role.SUPER_ADMIN, False),
        ("spoke", Role.EMPLOYEE, False),
        ("spoke", Role.ADMIN, False),
        ("spoke", Role.SUPER_ADMIN, False),
        ("admin", Role.EMPLOYEE, True),
        ("admin", Role.ADMIN, False),
        ("admin", Role.SUPER_ADMIN, False),
        ("super_admin", Role.EMPLOYEE, True),
        ("super_admin", Role.ADMIN, True),
        ("super_admin", Role.SUPER_ADMIN, True),
    ],
)
def test_approval_chain_matrix(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    approver_kind: str,
    requested: Role,
    allowed: bool,
) -> None:
    request = applicant(db, it, role=requested)
    actor = approver(db, it, approver_kind)
    headers = bearer(db, actor, clock, settings)
    approve = client.post(
        approve_url(request),
        json={"approved_role": requested.value, "approved_department": "IT"},
        headers=headers,
    )
    if allowed:
        assert approve.status_code == 200
    else:
        assert approve.status_code == 403
        assert error_code(approve) == "forbidden"
        reject = client.post(reject_url(request), json={"reason": "Not known"}, headers=headers)
        assert reject.status_code == 403
        db.refresh(request)
        assert request.status is SignupStatus.PENDING


def test_applicant_cannot_act_on_own_request(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    request = applicant(db, it)
    user = db.get(User, request.user_id)
    assert user is not None
    response = client.post(
        approve_url(request),
        json={"approved_role": "employee", "approved_department": "IT"},
        headers=bearer(db, user, clock, settings),
    )
    assert response.status_code == 401
    db.refresh(request)
    assert request.status is SignupStatus.PENDING


@pytest.mark.usefixtures("hr")
def test_approve_activates_user_with_changes(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
) -> None:
    published: list[SignupDecided] = []
    bus.register(SignupDecided, lambda _session, event: published.append(event))
    request = applicant(db, it, email="joiner@ibotix.ai")
    actor = make_user(db, it, role=Role.SUPER_ADMIN, name="Sam Super")
    response = client.post(
        approve_url(request),
        json={"approved_role": "admin", "approved_department": "HR"},
        headers=bearer(db, actor, clock, settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["approved_role"] == "admin"
    assert body["approved_department"] == "HR"
    assert body["requested_role"] == "employee"
    assert body["requested_department"] == "IT"
    assert body["decided_by"]["id"] == str(actor.id)
    assert body["decided_at"].endswith("Z")
    assert body["can_approve"] is False
    assert "rejection_reason" not in body
    user = db.get(User, request.user_id)
    assert user is not None
    db.refresh(user)
    assert user.state is AccountState.ACTIVE
    assert user.global_role is Role.ADMIN
    assert user.home_department_id == "HR"
    assert user.approved_by_id == actor.id
    assert user.approved_at == clock.now()
    emails = db.scalars(select(EmailOutbox).where(EmailOutbox.to_address == user.email))
    assert [row.template for row in emails] == ["signup_approved"]
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "signup_approved")).one()
    assert entry.is_security_limited is True
    assert entry.actor_id == actor.id
    assert [event.signup_request_id for event in published] == [request.id]


def test_approve_needs_authority_for_approved_role(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    request = applicant(db, it)
    admin = make_user(db, it, role=Role.ADMIN)
    response = client.post(
        approve_url(request),
        json={"approved_role": "admin", "approved_department": "IT"},
        headers=bearer(db, admin, clock, settings),
    )
    assert response.status_code == 403
    downgraded = applicant(db, it, role=Role.ADMIN)
    response = client.post(
        approve_url(downgraded),
        json={"approved_role": "employee", "approved_department": "IT"},
        headers=bearer(db, admin, clock, settings),
    )
    assert response.status_code == 403


def test_approve_validation(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    make_department(db, "OPS", "Operations", is_active=False)
    request = applicant(db, it)
    headers = bearer(db, make_user(db, it, role=Role.SUPER_ADMIN), clock, settings)
    spoke = client.post(
        approve_url(request),
        json={"approved_role": "spoke", "approved_department": "IT"},
        headers=headers,
    )
    assert spoke.status_code == 422
    assert "approved_role" in spoke.json()["error"]["fields"]
    inactive = client.post(
        approve_url(request),
        json={"approved_role": "employee", "approved_department": "OPS"},
        headers=headers,
    )
    assert inactive.status_code == 422
    assert "approved_department" in inactive.json()["error"]["fields"]


def test_reject_records_reason(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    published: list[SignupDecided] = []
    bus.register(SignupDecided, lambda _session, event: published.append(event))
    request = applicant(db, it, email="nope@ibotix.ai")
    admin = make_user(db, it, role=Role.ADMIN)
    response = client.post(
        reject_url(request),
        json={"reason": "  Unknown team member  "},
        headers=bearer(db, admin, clock, settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "Unknown team member"
    assert body["decided_by"]["id"] == str(admin.id)
    user = db.get(User, request.user_id)
    assert user is not None
    db.refresh(user)
    assert user.state is AccountState.REJECTED
    emails = list(db.scalars(select(EmailOutbox).where(EmailOutbox.to_address == user.email)))
    assert [row.template for row in emails] == ["signup_rejected"]
    assert "Unknown team member" in emails[0].body_text
    assert "signup_rejected" in list(db.scalars(select(AuditLog.action)))
    assert [event.signup_request_id for event in published] == [request.id]


@pytest.mark.parametrize("reason", ["", "four", "x" * 1001])
def test_reject_reason_length(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    reason: str,
) -> None:
    request = applicant(db, it)
    admin = make_user(db, it, role=Role.ADMIN)
    response = client.post(
        reject_url(request), json={"reason": reason}, headers=bearer(db, admin, clock, settings)
    )
    assert response.status_code == 422
    assert "reason" in response.json()["error"]["fields"]


def test_decided_request_conflicts(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    request = applicant(db, it)
    headers = bearer(db, make_user(db, it, role=Role.ADMIN), clock, settings)
    payload = {"approved_role": "employee", "approved_department": "IT"}
    assert client.post(approve_url(request), json=payload, headers=headers).status_code == 200
    again = client.post(approve_url(request), json=payload, headers=headers)
    assert again.status_code == 409
    assert error_code(again) == "conflict"
    rejected = client.post(reject_url(request), json={"reason": "Too late"}, headers=headers)
    assert rejected.status_code == 409


def test_unverified_request_cannot_be_decided(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    request = applicant(db, it, state=AccountState.PENDING_VERIFICATION)
    headers = bearer(db, make_user(db, it, role=Role.ADMIN), clock, settings)
    response = client.post(
        approve_url(request),
        json={"approved_role": "employee", "approved_department": "IT"},
        headers=headers,
    )
    assert response.status_code == 409


def test_unknown_request_is_not_found(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    headers = bearer(db, make_user(db, it, role=Role.ADMIN), clock, settings)
    for request_id in ["not-a-uuid", "00000000-0000-4000-8000-000000000000"]:
        response = client.post(
            f"{LIST}/{request_id}/reject", json={"reason": "Nobody here"}, headers=headers
        )
        assert response.status_code == 404
        assert error_code(response) == "not_found"


def test_list_requires_approver(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    for kind in ["employee", "spoke"]:
        response = client.get(LIST, headers=bearer(db, approver(db, it, kind), clock, settings))
        assert response.status_code == 403
        assert error_code(response) == "forbidden"
    assert client.get(LIST).status_code == 401


def test_list_filters_orders_and_flags(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    oldest = applicant(db, it, at_offset=timedelta(hours=-3))
    admin_request = applicant(db, it, role=Role.ADMIN, at_offset=timedelta(hours=-2))
    unverified = applicant(
        db,
        it,
        state=AccountState.PENDING_VERIFICATION,
        at_offset=timedelta(hours=-1),
    )
    decided = applicant(db, it, state=AccountState.REJECTED, at_offset=timedelta(minutes=-30))
    decided.status = SignupStatus.REJECTED
    decided.decision_reason = "Duplicate"
    db.flush()
    admin = make_user(db, it, role=Role.ADMIN)
    headers = bearer(db, admin, clock, settings)

    pending = client.get(LIST, params={"status": "pending"}, headers=headers)
    assert pending.status_code == 200
    body = pending.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 25
    assert [item["id"] for item in body["items"]] == [str(admin_request.id), str(oldest.id)]
    flags = {item["id"]: item["can_approve"] for item in body["items"]}
    assert flags == {str(admin_request.id): False, str(oldest.id): True}
    first = body["items"][1]
    assert first["email_verified"] is True
    assert first["requested_department"] == "IT"
    assert first["created_at"].endswith("Z")
    assert "approved_role" not in first

    everything = client.get(LIST, headers=headers).json()
    ids = [item["id"] for item in everything["items"]]
    assert ids == [str(decided.id), str(admin_request.id), str(oldest.id)]
    assert str(unverified.id) not in ids
    assert everything["items"][0]["rejection_reason"] == "Duplicate"
    assert everything["items"][0]["can_approve"] is False

    rejected = client.get(LIST, params={"status": "rejected"}, headers=headers).json()
    assert [item["id"] for item in rejected["items"]] == [str(decided.id)]

    paged = client.get(LIST, params={"page_size": 1, "page": 2}, headers=headers).json()
    assert paged["total"] == 3
    assert [item["id"] for item in paged["items"]] == [str(admin_request.id)]

    invalid = client.get(LIST, params={"status": "bogus"}, headers=headers)
    assert invalid.status_code == 422

    super_admin = make_user(db, it, role=Role.SUPER_ADMIN)
    super_view = client.get(
        LIST, params={"status": "pending"}, headers=bearer(db, super_admin, clock, settings)
    ).json()
    assert all(item["can_approve"] for item in super_view["items"])
