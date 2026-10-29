import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import (
    AccountState,
    ProtectedActionKind,
    ProtectedActionStatus,
    Role,
    TicketStatus,
)
from app.core.errors import ApiError
from app.core.events import ProtectedActionDecided, ProtectedActionRequested, bus
from app.core.security import create_access_token
from app.models import AuditLog, Department, ProtectedActionRequest, User
from app.services.me import MeService
from app.services.protected_actions import ProtectedActionService
from tests.factories import make_department, make_protected_action, make_ticket, make_user

ACTIONS = "/api/v1/protected-actions"
REASON = "Leaving the company"
PROTECTED_ACTION_KEYS = {
    "id",
    "kind",
    "target",
    "requested_by",
    "reason",
    "status",
    "created_at",
    "expires_at",
    "can_decide",
}


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


def super_admins(db: Session, department: Department, count: int) -> list[User]:
    return [
        make_user(db, department, role=Role.SUPER_ADMIN, name=f"Super {index}")
        for index in range(count)
    ]


def create_body(target: User, kind: ProtectedActionKind) -> dict[str, str]:
    return {"kind": kind.value, "target_user_id": str(target.id), "reason": REASON}


@pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.ADMIN])
def test_requires_superadmins_protect(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    role: Role,
) -> None:
    requester, target, _third = super_admins(db, it, 3)
    request = make_protected_action(db, target, requester)
    headers = bearer(db, make_user(db, it, role=role), clock, settings)
    assert client.get(ACTIONS, headers=headers).status_code == 403
    body = create_body(target, ProtectedActionKind.DEMOTE_SUPER_ADMIN)
    assert client.post(ACTIONS, json=body, headers=headers).status_code == 403
    assert client.post(f"{ACTIONS}/{request.id}/approve", headers=headers).status_code == 403
    rejected = client.post(
        f"{ACTIONS}/{request.id}/reject", json={"reason": REASON}, headers=headers
    )
    assert rejected.status_code == 403


def test_create(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    published: list[ProtectedActionRequested] = []
    bus.register(ProtectedActionRequested, lambda _session, event: published.append(event))
    requester, target, _third = super_admins(db, it, 3)
    response = client.post(
        ACTIONS,
        json=create_body(target, ProtectedActionKind.DEMOTE_SUPER_ADMIN),
        headers=bearer(db, requester, clock, settings),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == PROTECTED_ACTION_KEYS
    assert body["kind"] == "demote_super_admin"
    assert body["status"] == "pending"
    assert body["target"]["id"] == str(target.id)
    assert body["requested_by"]["id"] == str(requester.id)
    assert body["can_decide"] is False
    assert body["created_at"] == "2026-10-27T04:30:00Z"
    assert body["expires_at"] == "2026-10-30T04:30:00Z"
    request = db.scalars(select(ProtectedActionRequest)).one()
    assert request.expires_at == clock.now() + timedelta(hours=72)
    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == "protected_action_requested")
    ).one()
    assert entry.is_security_limited is True
    assert [event.protected_action_id for event in published] == [request.id]
    db.refresh(target)
    assert target.global_role is Role.SUPER_ADMIN


def test_create_target_rules(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester, target, _third = super_admins(db, it, 3)
    admin = make_user(db, it, role=Role.ADMIN)
    gone = make_user(db, it, role=Role.SUPER_ADMIN, state=AccountState.DEACTIVATED)
    headers = bearer(db, requester, clock, settings)
    kind = ProtectedActionKind.DEACTIVATE_SUPER_ADMIN
    for wrong in (admin, gone, requester):
        response = client.post(ACTIONS, json=create_body(wrong, kind), headers=headers)
        assert response.status_code == 422
        assert "target_user_id" in response.json()["error"]["fields"]
    garbage = client.post(
        ACTIONS,
        json={"kind": kind.value, "target_user_id": "nope", "reason": REASON},
        headers=headers,
    )
    assert garbage.status_code == 422
    bad_kind = client.post(
        ACTIONS,
        json={"kind": "delete_super_admin", "target_user_id": str(target.id), "reason": REASON},
        headers=headers,
    )
    assert bad_kind.status_code == 422
    short = client.post(
        ACTIONS,
        json={"kind": kind.value, "target_user_id": str(target.id), "reason": "no"},
        headers=headers,
    )
    assert short.status_code == 422

    first = client.post(ACTIONS, json=create_body(target, kind), headers=headers)
    assert first.status_code == 200
    duplicate = client.post(ACTIONS, json=create_body(target, kind), headers=headers)
    assert duplicate.status_code == 409
    assert error_code(duplicate) == "conflict"
    other_kind = client.post(
        ACTIONS,
        json=create_body(target, ProtectedActionKind.DEMOTE_SUPER_ADMIN),
        headers=headers,
    )
    assert other_kind.status_code == 200


def test_create_blocked_at_two(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester, target = super_admins(db, it, 2)
    response = client.post(
        ACTIONS,
        json=create_body(target, ProtectedActionKind.DEMOTE_SUPER_ADMIN),
        headers=bearer(db, requester, clock, settings),
    )
    assert response.status_code == 409
    assert error_code(response) == "protected_action_blocked"
    assert db.scalars(select(ProtectedActionRequest)).all() == []


def test_requester_and_target_cannot_decide(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester, target, _third = super_admins(db, it, 3)
    request = make_protected_action(db, target, requester)
    for person in (requester, target):
        headers = bearer(db, person, clock, settings)
        approve = client.post(f"{ACTIONS}/{request.id}/approve", headers=headers)
        assert approve.status_code == 403
        reject = client.post(
            f"{ACTIONS}/{request.id}/reject", json={"reason": REASON}, headers=headers
        )
        assert reject.status_code == 403
    db.refresh(request)
    assert request.status is ProtectedActionStatus.PENDING


def test_third_super_admin_approves_deactivation(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    published: list[ProtectedActionDecided] = []
    bus.register(ProtectedActionDecided, lambda _session, event: published.append(event))
    requester, target, third, _fourth = super_admins(db, it, 4)
    requester_of = make_user(db, it)
    make_ticket(db, requester_of, it, owner=target, status=TicketStatus.IN_PROGRESS)
    request = make_protected_action(db, target, requester)
    headers = bearer(db, third, clock, settings)

    listing = client.get(ACTIONS, headers=headers).json()
    assert listing["total"] == 1
    assert listing["items"][0]["can_decide"] is True

    response = client.post(f"{ACTIONS}/{request.id}/approve", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["decided_by"]["id"] == str(third.id)
    assert body["can_decide"] is False
    assert "decision_reason" not in body
    db.expire_all()
    user = db.get(User, target.id)
    assert user is not None
    assert user.state is AccountState.DEACTIVATED
    assert user.deactivated_by_id == third.id
    assert user.deactivation_reason == REASON
    assert user.global_role is Role.SUPER_ADMIN
    actions = set(db.scalars(select(AuditLog.action)))
    assert {"protected_action_approved", "user_deactivated"} <= actions
    approved = db.scalars(
        select(AuditLog).where(AuditLog.action == "protected_action_approved")
    ).one()
    assert approved.is_security_limited is True
    assert [event.protected_action_id for event in published] == [request.id]
    again = client.post(f"{ACTIONS}/{request.id}/approve", headers=headers)
    assert again.status_code == 409


def test_approve_demotion_sets_admin(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester, target, third = super_admins(db, it, 3)
    request = make_protected_action(
        db, target, requester, kind=ProtectedActionKind.DEMOTE_SUPER_ADMIN
    )
    response = client.post(
        f"{ACTIONS}/{request.id}/approve", headers=bearer(db, third, clock, settings)
    )
    assert response.status_code == 200
    db.refresh(target)
    assert target.global_role is Role.ADMIN
    assert target.state is AccountState.ACTIVE


def test_approve_rechecks_minimum(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    first_super, second_super, third_super = super_admins(db, it, 3)
    deactivate_second = make_protected_action(db, second_super, first_super)
    demote_third = make_protected_action(
        db, third_super, second_super, kind=ProtectedActionKind.DEMOTE_SUPER_ADMIN
    )
    approved = client.post(
        f"{ACTIONS}/{deactivate_second.id}/approve",
        headers=bearer(db, third_super, clock, settings),
    )
    assert approved.status_code == 200
    blocked = client.post(
        f"{ACTIONS}/{demote_third.id}/approve",
        headers=bearer(db, first_super, clock, settings),
    )
    assert blocked.status_code == 409
    assert error_code(blocked) == "protected_action_blocked"
    db.refresh(demote_third)
    db.refresh(third_super)
    assert demote_third.status is ProtectedActionStatus.PENDING
    assert third_super.global_role is Role.SUPER_ADMIN


def test_expired_request_cannot_be_decided(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester, target, third = super_admins(db, it, 3)
    request = make_protected_action(db, target, requester)
    clock.advance(timedelta(hours=72))
    headers = bearer(db, third, clock, settings)
    listing = client.get(ACTIONS, headers=headers).json()
    assert listing["items"][0]["can_decide"] is False
    approve = client.post(f"{ACTIONS}/{request.id}/approve", headers=headers)
    assert approve.status_code == 409
    reject = client.post(f"{ACTIONS}/{request.id}/reject", json={"reason": REASON}, headers=headers)
    assert reject.status_code == 409
    db.refresh(target)
    assert target.state is AccountState.ACTIVE


def test_reject(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester, target, third = super_admins(db, it, 3)
    request = make_protected_action(db, target, requester)
    headers = bearer(db, third, clock, settings)
    short = client.post(f"{ACTIONS}/{request.id}/reject", json={"reason": "no"}, headers=headers)
    assert short.status_code == 422
    response = client.post(
        f"{ACTIONS}/{request.id}/reject", json={"reason": "Still needed here"}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["decision_reason"] == "Still needed here"
    assert body["decided_by"]["id"] == str(third.id)
    db.refresh(target)
    assert target.state is AccountState.ACTIVE
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "protected_action_rejected")).one()
    assert entry.is_security_limited is True
    assert entry.reason == "Still needed here"
    again = client.post(f"{ACTIONS}/{request.id}/approve", headers=headers)
    assert again.status_code == 409
    missing = client.post(f"{ACTIONS}/not-a-uuid/approve", headers=headers)
    assert missing.status_code == 404


def test_list_filters_by_status(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    requester, target, third = super_admins(db, it, 3)
    make_protected_action(db, target, requester)
    make_protected_action(
        db,
        target,
        requester,
        kind=ProtectedActionKind.DEMOTE_SUPER_ADMIN,
        status=ProtectedActionStatus.REJECTED,
        at=clock.now() - timedelta(days=1),
    )
    headers = bearer(db, third, clock, settings)
    everything = client.get(ACTIONS, headers=headers).json()
    assert [item["status"] for item in everything["items"]] == ["pending", "rejected"]
    pending = client.get(ACTIONS, params={"status": "pending"}, headers=headers).json()
    assert pending["total"] == 1
    assert client.get(ACTIONS, params={"status": "bogus"}, headers=headers).status_code == 422


def test_concurrent_double_approval(
    committed_db: Session, migrated_engine: Engine, clock: FrozenClock
) -> None:
    department = make_department(committed_db, "IT")
    requester, target, first, second = super_admins(committed_db, department, 4)
    request = make_protected_action(committed_db, target, requester)
    committed_db.commit()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def approve(approver: User) -> None:
        with Session(bind=migrated_engine, autoflush=False, expire_on_commit=False) as session:
            actor = MeService(session).load_active_actor(approver.id)
            assert actor is not None
            barrier.wait()
            try:
                ProtectedActionService(session, clock).approve(actor, str(request.id))
                session.commit()
                outcome = "approved"
            except ApiError as error:
                session.rollback()
                outcome = error.code.value
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=approve, args=(user,)) for user in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(outcomes) == ["approved", "conflict"]
    committed_db.expire_all()
    stored = committed_db.get(ProtectedActionRequest, request.id)
    assert stored is not None
    assert stored.status is ProtectedActionStatus.APPROVED
    deactivations = committed_db.scalars(
        select(AuditLog).where(AuditLog.action == "user_deactivated")
    ).all()
    assert len(deactivations) == 1
    committed_db.rollback()
