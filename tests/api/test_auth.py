from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock, get_clock
from app.core.config import Environment, Settings
from app.core.db import get_db, transactional
from app.core.enums import AccountState, Role, SignupStatus
from app.core.security import create_access_token, hash_password, hash_token, verify_password
from app.main import create_app
from app.models import (
    AuditLog,
    Department,
    EmailOutbox,
    EmailToken,
    EmailTokenPurpose,
    RefreshToken,
    User,
)
from app.services.policy import PolicyService
from tests.factories import (
    make_department,
    make_email_token,
    make_policy_version,
    make_signup_request,
    make_spoke_assignment,
    make_user,
)

PASSWORD = "Correct-Horse-9"
NEW_PASSWORD = "Brand-New-Secret-7"
PASSWORD_HASH = hash_password(PASSWORD)
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
FORGOT = "/api/v1/auth/forgot-password"
RESET = "/api/v1/auth/reset-password"
PUBLIC_CONFIG = "/api/v1/public/config"
ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


def make_account(
    db: Session,
    department: Department,
    email: str = "alice@ibotix.ai",
    *,
    role: Role = Role.EMPLOYEE,
    state: AccountState = AccountState.ACTIVE,
) -> User:
    return make_user(
        db, department, email=email, role=role, state=state, password_hash=PASSWORD_HASH
    )


def login(client: TestClient, email: str = "alice@ibotix.ai", password: str = PASSWORD) -> Response:
    response: Response = client.post(LOGIN, json={"email": email, "password": password})
    return response


def bearer(user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def audit_actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)))


def error_code(response_json: object) -> str:
    assert isinstance(response_json, dict)
    error = response_json["error"]
    assert isinstance(error, dict)
    code = error["code"]
    assert isinstance(code, str)
    return code


def test_login_success_returns_me_and_sets_cookie(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_account(db, it, "Alice@ibotix.ai".lower())
    user.failed_login_count = 2
    db.flush()
    response = login(client, "  ALICE@ibotix.ai ")
    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 900
    assert body["access_token"]
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["roles"] == ["employee"]
    assert body["user"]["department_id"] == "IT"
    assert body["user"]["permissions"] == ["tickets.create"]
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("refresh_token=")
    assert "HttpOnly" in cookie
    assert "Path=/api/v1/auth" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=604800" in cookie
    assert "Secure" not in cookie
    db.refresh(user)
    assert user.failed_login_count == 0
    assert user.last_login_at == clock.now()
    stored = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)).one()
    assert stored.token_hash == hash_token(response.cookies["refresh_token"])
    assert "login_succeeded" in audit_actions(db)


def test_unknown_email_returns_invalid_credentials(client: TestClient, db: Session) -> None:
    response = login(client, "nobody@ibotix.ai")
    assert response.status_code == 401
    assert error_code(response.json()) == "invalid_credentials"
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "login_failed")).one()
    assert entry.actor_id is None


def test_wrong_password_returns_invalid_credentials(
    client: TestClient, db: Session, it: Department
) -> None:
    user = make_account(db, it)
    response = login(client, password="Wrong-Horse-99")
    assert response.status_code == 401
    assert error_code(response.json()) == "invalid_credentials"
    db.refresh(user)
    assert user.failed_login_count == 1
    assert "login_failed" in audit_actions(db)


def test_invalid_email_format_is_validation_error(client: TestClient) -> None:
    response = login(client, "not-an-email")
    assert response.status_code == 422
    assert error_code(response.json()) == "validation_error"


@pytest.mark.parametrize(
    "state",
    [AccountState.PENDING_VERIFICATION, AccountState.PENDING_APPROVAL, AccountState.DEACTIVATED],
)
def test_account_state_revealed_only_after_correct_password(
    client: TestClient, db: Session, it: Department, state: AccountState
) -> None:
    make_account(db, it, state=state)
    wrong = login(client, password="Wrong-Horse-99")
    assert wrong.status_code == 401
    assert error_code(wrong.json()) == "invalid_credentials"
    right = login(client)
    assert right.status_code == 403
    assert right.json()["error"]["code"] == "account_state"
    assert right.json()["error"]["details"] == {"state": state.value}
    assert "set-cookie" not in right.headers


def test_rejected_account_includes_rejection_reason(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_account(db, it, state=AccountState.REJECTED)
    request = make_signup_request(db, user, it, status=SignupStatus.REJECTED)
    request.decision_reason = "Unknown team"
    request.decided_at = clock.now()
    db.flush()
    response = login(client)
    assert response.status_code == 403
    assert response.json()["error"]["details"] == {
        "state": "rejected",
        "rejection_reason": "Unknown team",
    }


def test_lockout_after_five_failures_and_expiry(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_account(db, it)
    for _ in range(5):
        response = login(client, password="Wrong-Horse-99")
        assert response.status_code == 401
        assert error_code(response.json()) == "invalid_credentials"
    db.refresh(user)
    assert user.locked_until == clock.now() + timedelta(minutes=15)
    assert "account_locked" in audit_actions(db)
    locked = login(client)
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "too_many_attempts"
    assert locked.json()["error"]["details"] == {"retry_after_seconds": 900}
    clock.advance(timedelta(minutes=15, seconds=1))
    assert login(client).status_code == 200


def test_login_rate_limited_per_email(client: TestClient) -> None:
    for _ in range(10):
        assert login(client, "ghost@ibotix.ai").status_code == 401
    response = login(client, "ghost@ibotix.ai")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.json()["error"]["details"] == {"retry_after_seconds": 60}


def test_login_rate_limited_per_ip(client: TestClient) -> None:
    for number in range(10):
        assert login(client, f"ghost{number}@ibotix.ai").status_code == 401
    response = login(client, "another@ibotix.ai")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_rate_limit_window_resets(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    make_account(db, it)
    for _ in range(10):
        login(client, "ghost@ibotix.ai")
    clock.advance(timedelta(minutes=1))
    assert login(client).status_code == 200


def test_me_requires_token(client: TestClient) -> None:
    response = client.get(ME)
    assert response.status_code == 401
    assert error_code(response.json()) == "unauthenticated"


def test_me_rejects_garbage_and_tampered_tokens(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = make_account(db, it)
    assert client.get(ME, headers={"Authorization": "Bearer garbage"}).status_code == 401
    token = create_access_token(user.id, clock.now(), settings).token
    tampered = token[:-3] + ("abc" if not token.endswith("abc") else "xyz")
    response = client.get(ME, headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401
    assert error_code(response.json()) == "unauthenticated"


def test_me_rejects_expired_token(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = make_account(db, it)
    headers = bearer(user, clock, settings)
    assert client.get(ME, headers=headers).status_code == 200
    clock.advance(timedelta(minutes=15))
    response = client.get(ME, headers=headers)
    assert response.status_code == 401
    assert error_code(response.json()) == "unauthenticated"


def test_deactivated_users_token_is_refused(
    client: TestClient, db: Session, it: Department
) -> None:
    user = make_account(db, it)
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(ME, headers=headers).status_code == 200
    user.state = AccountState.DEACTIVATED
    db.flush()
    response = client.get(ME, headers=headers)
    assert response.status_code == 401
    assert error_code(response.json()) == "unauthenticated"


def test_me_for_employee(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = make_account(db, it)
    body = client.get(ME, headers=bearer(user, clock, settings)).json()
    assert body == {
        "id": str(user.id),
        "name": user.name,
        "email": "alice@ibotix.ai",
        "roles": ["employee"],
        "department_id": "IT",
        "spoke_departments": [],
        "permissions": ["tickets.create"],
        "mfa_enabled": False,
    }


def test_me_for_spoke(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    hr = make_department(db, "HR")
    user = make_account(db, it)
    make_spoke_assignment(db, user, hr)
    make_spoke_assignment(db, user, it)
    make_spoke_assignment(
        db, user, make_department(db, "FIN"), revoked_at=clock.now() - timedelta(days=1)
    )
    body = client.get(ME, headers=bearer(user, clock, settings)).json()
    assert body["roles"] == ["employee", "spoke"]
    assert body["spoke_departments"] == ["HR", "IT"]
    assert "tickets.view_department" in body["permissions"]
    assert "tickets.acknowledge" in body["permissions"]
    assert "tickets.view_all" not in body["permissions"]


@pytest.mark.parametrize("toggle", [True, False])
def test_me_for_admin_follows_policy_toggle(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    toggle: bool,
) -> None:
    config = dict(PolicyService(db).current_version().config)
    config["admins_can_manage_departments"] = toggle
    make_policy_version(db, 2, config)
    user = make_account(db, it, role=Role.ADMIN)
    body = client.get(ME, headers=bearer(user, clock, settings)).json()
    assert body["roles"] == ["employee", "admin"]
    permissions = set(body["permissions"])
    assert {"tickets.view_all", "users.approve_employee", "audit.view_all"} <= permissions
    assert ("departments.manage" in permissions) is toggle
    assert ("users.manage_roles" in permissions) is toggle
    assert "policy.manage" not in permissions
    assert "admins.manage" not in permissions


def test_me_for_super_admin_ignores_toggle(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    config = dict(PolicyService(db).current_version().config)
    config["admins_can_manage_departments"] = False
    make_policy_version(db, 2, config)
    user = make_account(db, it, role=Role.SUPER_ADMIN)
    body = client.get(ME, headers=bearer(user, clock, settings)).json()
    assert body["roles"] == ["employee", "super_admin"]
    permissions = set(body["permissions"])
    assert {
        "departments.manage",
        "users.manage_roles",
        "policy.manage",
        "admins.manage",
        "superadmins.protect",
        "confidential.manage",
        "users.approve_super_admin",
    } <= permissions


def test_refresh_rotates_token(client: TestClient, db: Session, it: Department) -> None:
    make_account(db, it)
    first = login(client).cookies["refresh_token"]
    response = client.post(REFRESH)
    assert response.status_code == 200
    assert response.json()["expires_in"] == 900
    assert response.json()["access_token"]
    second = response.cookies["refresh_token"]
    assert second != first
    old = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(first)))
    new = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(second)))
    old_token = old.one()
    new_token = new.one()
    assert old_token.revoked_at is not None
    assert old_token.replaced_by_id == new_token.id
    assert old_token.family_id == new_token.family_id
    assert new_token.revoked_at is None


def test_refresh_reuse_revokes_family(client: TestClient, db: Session, it: Department) -> None:
    make_account(db, it)
    first = login(client).cookies["refresh_token"]
    second = client.post(REFRESH).cookies["refresh_token"]
    client.cookies.clear()
    reused = client.post(REFRESH, headers={"Cookie": f"refresh_token={first}"})
    assert reused.status_code == 401
    assert error_code(reused.json()) == "unauthenticated"
    assert "refresh_reuse_detected" in audit_actions(db)
    after = client.post(REFRESH, headers={"Cookie": f"refresh_token={second}"})
    assert after.status_code == 401
    tokens = db.scalars(select(RefreshToken)).all()
    assert all(token.revoked_at is not None for token in tokens)


def test_refresh_without_cookie_or_unknown_cookie(client: TestClient) -> None:
    assert client.post(REFRESH).status_code == 401
    response = client.post(REFRESH, headers={"Cookie": "refresh_token=unknown"})
    assert response.status_code == 401
    assert error_code(response.json()) == "unauthenticated"


def test_refresh_expired_token(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    make_account(db, it)
    login(client)
    clock.advance(timedelta(days=7))
    response = client.post(REFRESH)
    assert response.status_code == 401
    assert error_code(response.json()) == "unauthenticated"


def test_refresh_for_deactivated_user(client: TestClient, db: Session, it: Department) -> None:
    user = make_account(db, it)
    login(client)
    user.state = AccountState.DEACTIVATED
    db.flush()
    assert client.post(REFRESH).status_code == 401


def test_refresh_and_logout_reject_foreign_origin(
    client: TestClient, db: Session, it: Department
) -> None:
    make_account(db, it)
    login(client)
    headers = {"Origin": "http://evil.example"}
    refresh = client.post(REFRESH, headers=headers)
    assert refresh.status_code == 403
    assert error_code(refresh.json()) == "forbidden"
    logout = client.post(LOGOUT, headers=headers)
    assert logout.status_code == 403
    assert client.post(REFRESH, headers={"Origin": ALLOWED_ORIGIN}).status_code == 200


def test_logout_revokes_and_clears_cookie(client: TestClient, db: Session, it: Department) -> None:
    make_account(db, it)
    token = login(client).cookies["refresh_token"]
    response = client.post(LOGOUT)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("refresh_token=")
    assert "Max-Age=0" in cookie
    assert "Path=/api/v1/auth" in cookie
    assert "logout" in audit_actions(db)
    stored = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token)))
    assert stored.one().revoked_at is not None
    client.cookies.clear()
    again = client.post(REFRESH, headers={"Cookie": f"refresh_token={token}"})
    assert again.status_code == 401
    assert "refresh_reuse_detected" not in audit_actions(db)


def test_logout_without_cookie_is_204(client: TestClient) -> None:
    assert client.post(LOGOUT).status_code == 204


@pytest.fixture
def secure_client(db: Session, clock: FrozenClock) -> Iterator[TestClient]:
    app = create_app(Settings(env=Environment.TEST, cookie_secure=True, cookie_samesite="strict"))

    def override_db() -> Iterator[Session]:
        yield from transactional(db)

    def override_clock() -> Clock:
        return clock

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_clock] = override_clock
    with TestClient(app) as test_client:
        yield test_client


def test_cookie_secure_and_samesite_follow_settings(
    secure_client: TestClient, db: Session, it: Department
) -> None:
    make_account(db, it)
    cookie = login(secure_client).headers["set-cookie"]
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "HttpOnly" in cookie


def test_forgot_password_enqueues_reset_email(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_account(db, it)
    response = client.post(FORGOT, json={"email": "Alice@ibotix.ai"})
    assert response.status_code == 202
    token = db.scalars(select(EmailToken).where(EmailToken.user_id == user.id)).one()
    assert token.purpose is EmailTokenPurpose.RESET
    assert token.expires_at == clock.now() + timedelta(hours=1)
    email = db.scalars(select(EmailOutbox)).one()
    assert email.to_address == "alice@ibotix.ai"
    assert email.template == "password_reset"
    raw = email.context["token"]
    assert isinstance(raw, str)
    assert email.context["expires_minutes"] == 60
    assert email.subject == "Reset your password"
    assert f"/reset-password?token={raw}" in email.body_text
    assert token.token_hash == hash_token(raw)
    assert raw not in token.token_hash


@pytest.mark.parametrize("state", [AccountState.PENDING_APPROVAL, AccountState.DEACTIVATED])
def test_forgot_password_ignores_inactive_and_unknown(
    client: TestClient, db: Session, it: Department, state: AccountState
) -> None:
    make_account(db, it, state=state)
    assert client.post(FORGOT, json={"email": "alice@ibotix.ai"}).status_code == 202
    assert client.post(FORGOT, json={"email": "nobody@ibotix.ai"}).status_code == 202
    assert db.scalars(select(EmailOutbox)).first() is None
    assert db.scalars(select(EmailToken)).first() is None


def test_forgot_password_rate_limited(client: TestClient, db: Session, it: Department) -> None:
    make_account(db, it)
    for _ in range(3):
        assert client.post(FORGOT, json={"email": "alice@ibotix.ai"}).status_code == 202
    response = client.post(FORGOT, json={"email": "alice@ibotix.ai"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.json()["error"]["details"]["retry_after_seconds"] > 0
    assert len(db.scalars(select(EmailOutbox)).all()) == 3


def test_reset_password_flow(client: TestClient, db: Session, it: Department) -> None:
    user = make_account(db, it)
    old_refresh = login(client).cookies["refresh_token"]
    user.failed_login_count = 3
    db.flush()
    make_email_token(db, user, purpose=EmailTokenPurpose.RESET, raw_token="reset-raw-token")
    response = client.post(RESET, json={"token": "reset-raw-token", "password": NEW_PASSWORD})
    assert response.status_code == 204
    db.refresh(user)
    assert verify_password(user.password_hash, NEW_PASSWORD)
    assert user.failed_login_count == 0
    assert "password_reset" in audit_actions(db)
    stored = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(old_refresh))
    ).one()
    assert stored.revoked_at is not None
    client.cookies.clear()
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200
    reused = client.post(RESET, json={"token": "reset-raw-token", "password": NEW_PASSWORD})
    assert reused.status_code == 422


def test_reset_password_expired_token(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_account(db, it)
    make_email_token(
        db,
        user,
        purpose=EmailTokenPurpose.RESET,
        raw_token="reset-raw-token",
        lifetime=timedelta(hours=1),
    )
    clock.advance(timedelta(hours=1, seconds=1))
    response = client.post(RESET, json={"token": "reset-raw-token", "password": NEW_PASSWORD})
    assert response.status_code == 410
    assert error_code(response.json()) == "token_expired"


def test_reset_password_invalid_token(client: TestClient, db: Session, it: Department) -> None:
    user = make_account(db, it)
    make_email_token(db, user, purpose=EmailTokenPurpose.VERIFY, raw_token="verify-token")
    for token in ("unknown-token", "verify-token"):
        response = client.post(RESET, json={"token": token, "password": NEW_PASSWORD})
        assert response.status_code == 422
        assert "token" in response.json()["error"]["fields"]


def test_reset_password_enforces_policy(client: TestClient, db: Session, it: Department) -> None:
    user = make_account(db, it)
    make_email_token(db, user, purpose=EmailTokenPurpose.RESET, raw_token="reset-raw-token")
    response = client.post(RESET, json={"token": "reset-raw-token", "password": "weakpassword"})
    assert response.status_code == 422
    assert error_code(response.json()) == "validation_error"
    assert "password" in response.json()["error"]["fields"]


def test_public_config(client: TestClient, db: Session) -> None:
    make_department(db, "IT", "Information Technology")
    make_department(db, "HR", "Human Resources")
    make_department(db, "OLD", "Archived", is_active=False)
    response = client.get(PUBLIC_CONFIG, headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 200
    assert response.json() == {
        "allowed_email_domains": ["ibotix.ai"],
        "departments": [
            {"id": "HR", "name": "Human Resources"},
            {"id": "IT", "name": "Information Technology"},
        ],
        "attachment_limits": {
            "max_bytes": 10485760,
            "max_files": 5,
            "allowed_mime_types": Settings(env=Environment.TEST).allowed_content_types,
        },
        "password_min_length": 12,
        "first_response_hours": 24,
    }


def test_public_endpoints_never_return_401(client: TestClient) -> None:
    headers = {"Authorization": "Bearer garbage"}
    assert client.get(PUBLIC_CONFIG, headers=headers).status_code == 200
    assert client.post(FORGOT, json={"email": "x@ibotix.ai"}, headers=headers).status_code == 202
    reset = client.post(RESET, json={"token": "nope", "password": NEW_PASSWORD}, headers=headers)
    assert reset.status_code == 422
