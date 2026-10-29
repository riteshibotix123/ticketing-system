from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.enums import AccountState, Role, SignupStatus
from app.core.events import SignupVerified, bus
from app.core.security import hash_password, hash_token, verify_password
from app.models import AuditLog, Department, EmailOutbox, EmailToken, SignupRequest, User
from tests.factories import make_department, make_email_token, make_signup_request, make_user

PASSWORD = "Correct-Horse-9"
PASSWORD_HASH = hash_password(PASSWORD)
SIGNUP = "/api/v1/auth/signup"
VERIFY = "/api/v1/auth/verify-email"
RESEND = "/api/v1/auth/resend-verification"
REAPPLY = "/api/v1/auth/reapply"
GENERIC = {"message": "If the details are valid, check your email to continue."}


@pytest.fixture(autouse=True)
def departments(db: Session) -> dict[str, Department]:
    created = {
        "IT": make_department(db, "IT", "Information Technology"),
        "HR": make_department(db, "HR", "Human Resources"),
    }
    db.commit()
    return created


@pytest.fixture
def it(departments: dict[str, Department]) -> Department:
    return departments["IT"]


def signup_body(
    email: str = "new.person@ibotix.ai",
    *,
    name: str = "New Person",
    password: str = PASSWORD,
    role: str = "employee",
    department: str = "IT",
) -> dict[str, str]:
    return {
        "name": name,
        "email": email,
        "password": password,
        "requested_role": role,
        "requested_department": department,
    }


def reapply_body(
    email: str = "rejected@ibotix.ai",
    *,
    password: str = PASSWORD,
    role: str = "employee",
    department: str = "HR",
) -> dict[str, str]:
    return {
        "email": email,
        "password": password,
        "requested_role": role,
        "requested_department": department,
    }


def emails_to(db: Session, address: str) -> list[EmailOutbox]:
    statement = (
        select(EmailOutbox)
        .where(EmailOutbox.to_address == address)
        .order_by(EmailOutbox.created_at, EmailOutbox.id)
    )
    return list(db.scalars(statement))


def last_token(db: Session, address: str) -> str:
    live = set(db.scalars(select(EmailToken.token_hash).where(EmailToken.used_at.is_(None))))
    for row in emails_to(db, address):
        context = row.context
        if row.template == "verify_email" and isinstance(context, dict):
            token = context["token"]
            if isinstance(token, str) and hash_token(token) in live:
                return token
    raise AssertionError("no live verification token")


def error(response: Response) -> dict[str, object]:
    body = response.json()
    assert isinstance(body, dict)
    payload = body["error"]
    assert isinstance(payload, dict)
    return payload


def audit_actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.action)))


def rejected_user(db: Session, department: Department, email: str = "rejected@ibotix.ai") -> User:
    user = make_user(
        db, department, email=email, state=AccountState.REJECTED, password_hash=PASSWORD_HASH
    )
    make_signup_request(db, user, department, status=SignupStatus.REJECTED)
    db.commit()
    return user


def test_signup_creates_pending_user_request_and_email(
    client: TestClient, db: Session, clock: FrozenClock
) -> None:
    response = client.post(SIGNUP, json=signup_body("  New.Person@IBOTIX.ai ", role="admin"))
    assert response.status_code == 202
    assert response.json() == GENERIC
    user = db.scalars(select(User).where(User.email == "new.person@ibotix.ai")).one()
    assert user.state is AccountState.PENDING_VERIFICATION
    assert user.global_role is Role.EMPLOYEE
    assert user.home_department_id == "IT"
    assert user.email_verified_at is None
    assert verify_password(user.password_hash, PASSWORD)
    request = db.scalars(select(SignupRequest).where(SignupRequest.user_id == user.id)).one()
    assert request.status is SignupStatus.PENDING
    assert request.requested_role is Role.ADMIN
    assert request.requested_department_id == "IT"
    token = db.scalars(select(EmailToken).where(EmailToken.user_id == user.id)).one()
    assert token.expires_at == clock.now() + timedelta(hours=24)
    raw = last_token(db, user.email)
    assert token.token_hash != raw
    assert len(token.token_hash) == 64
    assert "signup_requested" in audit_actions(db)


def test_existing_email_gets_identical_response_and_notice(
    client: TestClient, db: Session, it: Department
) -> None:
    make_user(db, it, email="taken@ibotix.ai")
    new = client.post(SIGNUP, json=signup_body("fresh@ibotix.ai"))
    existing = client.post(SIGNUP, json=signup_body("taken@ibotix.ai", name="Someone Else"))
    assert new.status_code == existing.status_code == 202
    assert new.json() == existing.json() == GENERIC
    assert [row.template for row in emails_to(db, "taken@ibotix.ai")] == ["account_exists_notice"]
    assert db.scalars(select(User).where(User.email == "taken@ibotix.ai")).one().name != (
        "Someone Else"
    )


def test_existing_pending_verification_email_is_resent(client: TestClient, db: Session) -> None:
    assert client.post(SIGNUP, json=signup_body()).status_code == 202
    first = last_token(db, "new.person@ibotix.ai")
    response = client.post(SIGNUP, json=signup_body())
    assert response.status_code == 202
    assert response.json() == GENERIC
    second = last_token(db, "new.person@ibotix.ai")
    assert first != second
    assert db.scalars(select(User).where(User.email == "new.person@ibotix.ai")).one()
    old = client.post(VERIFY, json={"token": first})
    assert old.status_code == 422
    assert client.post(VERIFY, json={"token": second}).status_code == 200


def test_signup_rejects_other_domains(client: TestClient, db: Session) -> None:
    response = client.post(SIGNUP, json=signup_body("person@gmail.com"))
    assert response.status_code == 422
    payload = error(response)
    assert payload["code"] == "validation_error"
    fields = payload["fields"]
    assert isinstance(fields, dict)
    assert "ibotix.ai" in fields["email"]
    assert db.scalars(select(User)).first() is None


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (signup_body(password="short"), "password"),
        (signup_body(password="alllowercase123"), "password"),
        (signup_body(name="A"), "name"),
        (signup_body(role="spoke"), "requested_role"),
        (signup_body(role="resolver"), "requested_role"),
        (signup_body(department="XX"), "requested_department"),
        (signup_body(department="OPS"), "requested_department"),
        (signup_body("not-an-email"), "email"),
    ],
)
def test_signup_validation(
    client: TestClient, db: Session, body: dict[str, str], field: str
) -> None:
    make_department(db, "OPS", "Operations", is_active=False)
    response = client.post(SIGNUP, json=body)
    assert response.status_code == 422
    fields = error(response)["fields"]
    assert isinstance(fields, dict)
    assert field in fields


def test_signup_rate_limited_per_email(client: TestClient) -> None:
    for _ in range(5):
        assert client.post(SIGNUP, json=signup_body()).status_code == 202
    response = client.post(SIGNUP, json=signup_body())
    assert response.status_code == 429
    assert error(response)["code"] == "rate_limited"


def test_signup_rate_limited_per_ip(client: TestClient) -> None:
    for number in range(5):
        response = client.post(SIGNUP, json=signup_body(f"person{number}@ibotix.ai"))
        assert response.status_code == 202
    response = client.post(SIGNUP, json=signup_body("person9@ibotix.ai"))
    assert response.status_code == 429
    details = error(response)["details"]
    assert isinstance(details, dict)
    assert details["retry_after_seconds"] > 0


def test_verify_email_moves_to_pending_approval(
    client: TestClient, db: Session, clock: FrozenClock
) -> None:
    published: list[SignupVerified] = []
    bus.register(SignupVerified, lambda _session, event: published.append(event))
    client.post(SIGNUP, json=signup_body())
    token = last_token(db, "new.person@ibotix.ai")
    response = client.post(VERIFY, json={"token": token})
    assert response.status_code == 200
    assert response.json() == {"state": "pending_approval"}
    user = db.scalars(select(User).where(User.email == "new.person@ibotix.ai")).one()
    assert user.state is AccountState.PENDING_APPROVAL
    assert user.email_verified_at == clock.now()
    request = db.scalars(select(SignupRequest).where(SignupRequest.user_id == user.id)).one()
    assert [event.signup_request_id for event in published] == [request.id]
    assert "email_verified" in audit_actions(db)
    reused = client.post(VERIFY, json={"token": token})
    assert reused.status_code == 422
    fields = error(reused)["fields"]
    assert isinstance(fields, dict)
    assert "token" in fields


def test_verify_unknown_token(client: TestClient) -> None:
    response = client.post(VERIFY, json={"token": "nope"})
    assert response.status_code == 422
    assert error(response)["code"] == "validation_error"


def test_verify_expired_token(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_user(db, it, state=AccountState.PENDING_VERIFICATION)
    make_signup_request(db, user, it)
    make_email_token(db, user, raw_token="expiring-token")
    db.commit()
    clock.advance(timedelta(hours=24))
    response = client.post(VERIFY, json={"token": "expiring-token"})
    assert response.status_code == 410
    assert error(response)["code"] == "token_expired"
    db.refresh(user)
    assert user.state is AccountState.PENDING_VERIFICATION


def test_resend_issues_new_token_and_invalidates_old(client: TestClient, db: Session) -> None:
    client.post(SIGNUP, json=signup_body())
    first = last_token(db, "new.person@ibotix.ai")
    response = client.post(RESEND, json={"email": "new.person@ibotix.ai"})
    assert response.status_code == 202
    second = last_token(db, "new.person@ibotix.ai")
    assert first != second
    assert client.post(VERIFY, json={"token": first}).status_code == 422
    assert client.post(VERIFY, json={"token": second}).status_code == 200


@pytest.mark.parametrize("state", [AccountState.ACTIVE, AccountState.PENDING_APPROVAL])
def test_resend_is_silent_for_other_accounts(
    client: TestClient, db: Session, it: Department, state: AccountState
) -> None:
    make_user(db, it, email="other@ibotix.ai", state=state)
    assert client.post(RESEND, json={"email": "other@ibotix.ai"}).status_code == 202
    assert client.post(RESEND, json={"email": "nobody@ibotix.ai"}).status_code == 202
    assert emails_to(db, "other@ibotix.ai") == []
    assert emails_to(db, "nobody@ibotix.ai") == []


def test_resend_rate_limited(client: TestClient) -> None:
    for _ in range(3):
        assert client.post(RESEND, json={"email": "a@ibotix.ai"}).status_code == 202
    response = client.post(RESEND, json={"email": "a@ibotix.ai"})
    assert response.status_code == 429
    assert error(response)["code"] == "rate_limited"


def test_reapply_creates_new_pending_request(
    client: TestClient, db: Session, it: Department
) -> None:
    published: list[SignupVerified] = []
    bus.register(SignupVerified, lambda _session, event: published.append(event))
    user = rejected_user(db, it)
    response = client.post(REAPPLY, json=reapply_body(role="admin"))
    assert response.status_code == 202
    db.refresh(user)
    assert user.state is AccountState.PENDING_APPROVAL
    assert user.home_department_id == "HR"
    pending = db.scalars(
        select(SignupRequest).where(
            SignupRequest.user_id == user.id, SignupRequest.status == SignupStatus.PENDING
        )
    ).one()
    assert pending.requested_role is Role.ADMIN
    assert pending.requested_department_id == "HR"
    assert [event.signup_request_id for event in published] == [pending.id]
    assert "signup_reapplied" in audit_actions(db)


def test_reapply_wrong_password_is_forbidden_not_401(
    client: TestClient, db: Session, it: Department
) -> None:
    user = rejected_user(db, it)
    response = client.post(REAPPLY, json=reapply_body(password="Wrong-Horse-99"))
    assert response.status_code == 403
    payload = error(response)
    assert payload["code"] == "forbidden"
    fields = payload["fields"]
    assert isinstance(fields, dict)
    assert "password" in fields
    db.refresh(user)
    assert user.failed_login_count == 1
    assert user.state is AccountState.REJECTED


def test_reapply_unknown_email_looks_like_wrong_password(client: TestClient) -> None:
    response = client.post(REAPPLY, json=reapply_body("ghost@ibotix.ai"))
    assert response.status_code == 403
    assert error(response)["code"] == "forbidden"


def test_reapply_lockout(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    rejected_user(db, it)
    for _ in range(5):
        assert client.post(REAPPLY, json=reapply_body(password="Wrong-Horse-99")).status_code == (
            403
        )
    locked = client.post(REAPPLY, json=reapply_body())
    assert locked.status_code == 429
    assert error(locked)["code"] == "too_many_attempts"
    assert "account_locked" in audit_actions(db)
    clock.advance(timedelta(minutes=15, seconds=1))
    assert client.post(REAPPLY, json=reapply_body()).status_code == 202


@pytest.mark.parametrize(
    "state", [AccountState.ACTIVE, AccountState.PENDING_APPROVAL, AccountState.DEACTIVATED]
)
def test_reapply_only_for_rejected(
    client: TestClient, db: Session, it: Department, state: AccountState
) -> None:
    make_user(db, it, email="rejected@ibotix.ai", state=state, password_hash=PASSWORD_HASH)
    response = client.post(REAPPLY, json=reapply_body())
    assert response.status_code == 409
    assert error(response)["code"] == "conflict"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (reapply_body("rejected@gmail.com"), "email"),
        (reapply_body(role="spoke"), "requested_role"),
        (reapply_body(department="ZZ"), "requested_department"),
    ],
)
def test_reapply_validation(
    client: TestClient,
    db: Session,
    it: Department,
    body: dict[str, str],
    field: str,
) -> None:
    rejected_user(db, it)
    response = client.post(REAPPLY, json=body)
    assert response.status_code == 422
    fields = error(response)["fields"]
    assert isinstance(fields, dict)
    assert field in fields


def test_public_signup_endpoints_never_return_401(
    client: TestClient, db: Session, it: Department
) -> None:
    rejected_user(db, it)
    headers = {"Authorization": "Bearer not-a-token"}
    responses = [
        client.post(SIGNUP, json=signup_body(), headers=headers),
        client.post(SIGNUP, json={}, headers=headers),
        client.post(VERIFY, json={"token": "bad"}, headers=headers),
        client.post(RESEND, json={"email": "x@ibotix.ai"}, headers=headers),
        client.post(REAPPLY, json=reapply_body(password="Wrong-Horse-99"), headers=headers),
        client.post(REAPPLY, json=reapply_body("ghost@ibotix.ai"), headers=headers),
        client.post(REAPPLY, json=reapply_body(), headers=headers),
    ]
    assert all(response.status_code != 401 for response in responses)
