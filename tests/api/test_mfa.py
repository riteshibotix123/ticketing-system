from collections.abc import Iterator
from datetime import timedelta

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock, get_clock
from app.core.config import Environment, MfaRole, Settings
from app.core.db import get_db, transactional
from app.core.enums import Role
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models import AuditLog, Department, MfaRecoveryCode, User
from tests.factories import make_department, make_spoke_assignment, make_user

PASSWORD = "Correct-Horse-9"
PASSWORD_HASH = hash_password(PASSWORD)
ENCRYPTION_KEY = Fernet.generate_key().decode()
LOGIN = "/api/v1/auth/login"
SETUP = "/api/v1/auth/mfa/setup"
CONFIRM = "/api/v1/auth/mfa/confirm"
VERIFY = "/api/v1/auth/mfa/verify"
ME = "/api/v1/auth/me"


def mfa_settings(*roles: MfaRole) -> Settings:
    return Settings(
        env=Environment.TEST,
        mfa_required_roles=list(roles),
        field_encryption_key=SecretStr(ENCRYPTION_KEY),
    )


@pytest.fixture
def settings() -> Settings:
    return mfa_settings("admin", "super_admin")


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


def make_account(db: Session, department: Department, email: str, role: Role) -> User:
    return make_user(db, department, email=email, role=role, password_hash=PASSWORD_HASH)


def login(client: TestClient, email: str) -> Response:
    response: Response = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    return response


def body_of(response: Response) -> dict[str, object]:
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def error_code(response: Response) -> str:
    error = body_of(response)["error"]
    assert isinstance(error, dict)
    code = error["code"]
    assert isinstance(code, str)
    return code


def text_field(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    assert isinstance(value, str)
    return value


def enrol(client: TestClient, email: str, clock: Clock) -> tuple[str, list[str]]:
    token = text_field(body_of(login(client, email)), "mfa_token")
    secret = text_field(body_of(client.post(SETUP, json={"mfa_token": token})), "secret")
    code = pyotp.TOTP(secret).at(clock.now())
    confirmed = body_of(client.post(CONFIRM, json={"mfa_token": token, "code": code}))
    codes = confirmed["recovery_codes"]
    assert isinstance(codes, list)
    return secret, [str(item) for item in codes]


def challenge_token(client: TestClient, email: str) -> str:
    payload = body_of(login(client, email))
    assert payload["mfa_required"] is True
    return text_field(payload, "mfa_token")


def test_enrolment_flow_returns_login_success_and_recovery_codes(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()

    first = login(client, "admin@ibotix.ai")
    assert first.status_code == 200
    payload = body_of(first)
    assert set(payload) == {"mfa_enrol_required", "mfa_token"}
    assert payload["mfa_enrol_required"] is True
    assert "refresh_token" not in first.cookies
    token = text_field(payload, "mfa_token")

    setup = client.post(SETUP, json={"mfa_token": token})
    assert setup.status_code == 200
    setup_body = body_of(setup)
    secret = text_field(setup_body, "secret")
    assert text_field(setup_body, "otpauth_uri").startswith("otpauth://totp/")
    db.refresh(user)
    assert user.mfa_secret_encrypted is not None
    assert secret not in user.mfa_secret_encrypted
    assert user.mfa_enabled is False

    confirm = client.post(
        CONFIRM, json={"mfa_token": token, "code": pyotp.TOTP(secret).at(clock.now())}
    )
    assert confirm.status_code == 200
    confirmed = body_of(confirm)
    assert set(confirmed) == {"access_token", "expires_in", "user", "recovery_codes"}
    codes = confirmed["recovery_codes"]
    assert isinstance(codes, list)
    assert len(codes) == 8
    assert len(set(map(str, codes))) == 8
    assert "refresh_token" in confirm.cookies
    me = confirmed["user"]
    assert isinstance(me, dict)
    assert me["mfa_enabled"] is True

    stored = list(db.scalars(select(MfaRecoveryCode.code_hash)))
    assert len(stored) == 8
    assert not set(map(str, codes)) & set(stored)
    actions = set(db.scalars(select(AuditLog.action)))
    assert {"mfa_enabled", "login_succeeded"} <= actions


def test_confirm_rejects_wrong_code_and_setup_refuses_when_enabled(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()
    token = text_field(body_of(login(client, "admin@ibotix.ai")), "mfa_token")
    assert client.post(CONFIRM, json={"mfa_token": token, "code": "123456"}).status_code == 409
    secret = text_field(body_of(client.post(SETUP, json={"mfa_token": token})), "secret")
    wrong = pyotp.TOTP(secret).at(clock.now() + timedelta(minutes=5))

    rejected = client.post(CONFIRM, json={"mfa_token": token, "code": wrong})
    assert rejected.status_code == 422
    assert error_code(rejected) == "validation_error"

    good = pyotp.TOTP(secret).at(clock.now())
    assert client.post(CONFIRM, json={"mfa_token": token, "code": good}).status_code == 200
    again = client.post(SETUP, json={"mfa_token": token})
    assert again.status_code == 409
    assert error_code(again) == "conflict"


def test_enrolled_user_gets_mfa_required_and_verify_succeeds(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()
    secret, _ = enrol(client, "admin@ibotix.ai", clock)
    clock.advance(timedelta(minutes=1))

    token = challenge_token(client, "admin@ibotix.ai")
    verified = client.post(
        VERIFY, json={"mfa_token": token, "code": pyotp.TOTP(secret).at(clock.now())}
    )
    assert verified.status_code == 200
    assert set(body_of(verified)) == {"access_token", "expires_in", "user"}
    assert "refresh_token" in verified.cookies


def test_code_window_is_one_step(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()
    secret, _ = enrol(client, "admin@ibotix.ai", clock)
    totp = pyotp.TOTP(secret)
    token = challenge_token(client, "admin@ibotix.ai")

    stale = client.post(
        VERIFY, json={"mfa_token": token, "code": totp.at(clock.now() - timedelta(seconds=90))}
    )
    assert stale.status_code == 422
    early = client.post(
        VERIFY, json={"mfa_token": token, "code": totp.at(clock.now() + timedelta(seconds=90))}
    )
    assert early.status_code == 422
    previous = client.post(
        VERIFY, json={"mfa_token": token, "code": totp.at(clock.now() - timedelta(seconds=30))}
    )
    assert previous.status_code == 200


def test_recovery_code_is_single_use(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()
    _, codes = enrol(client, "admin@ibotix.ai", clock)

    token = challenge_token(client, "admin@ibotix.ai")
    first = client.post(VERIFY, json={"mfa_token": token, "code": codes[0].upper()})
    assert first.status_code == 200
    second = client.post(VERIFY, json={"mfa_token": token, "code": codes[0]})
    assert second.status_code == 422
    assert client.post(VERIFY, json={"mfa_token": token, "code": codes[1]}).status_code == 200
    actions = list(db.scalars(select(AuditLog.action)))
    assert actions.count("mfa_recovery_code_used") == 2


def test_five_failures_lock_the_account(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()
    secret, _ = enrol(client, "admin@ibotix.ai", clock)
    token = challenge_token(client, "admin@ibotix.ai")

    for _ in range(4):
        failed = client.post(VERIFY, json={"mfa_token": token, "code": "000000x"})
        assert failed.status_code == 422
    locked = client.post(VERIFY, json={"mfa_token": token, "code": "000000x"})
    assert locked.status_code == 429
    assert error_code(locked) == "too_many_attempts"
    details = body_of(locked)["error"]
    assert isinstance(details, dict)
    assert details["details"] == {"retry_after_seconds": 900}

    good = pyotp.TOTP(secret).at(clock.now())
    assert client.post(VERIFY, json={"mfa_token": token, "code": good}).status_code == 429
    assert login(client, "admin@ibotix.ai").status_code == 429
    db.refresh(user)
    assert user.locked_until == clock.now() + timedelta(minutes=15)

    clock.advance(timedelta(minutes=15, seconds=1))
    fresh = challenge_token(client, "admin@ibotix.ai")
    code = pyotp.TOTP(secret).at(clock.now())
    assert client.post(VERIFY, json={"mfa_token": fresh, "code": code}).status_code == 200


def test_success_resets_consecutive_failures(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    user = make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()
    secret, _ = enrol(client, "admin@ibotix.ai", clock)
    token = challenge_token(client, "admin@ibotix.ai")
    for _ in range(4):
        client.post(VERIFY, json={"mfa_token": token, "code": "999999"})
    code = pyotp.TOTP(secret).at(clock.now())
    assert client.post(VERIFY, json={"mfa_token": token, "code": code}).status_code == 200
    db.refresh(user)
    assert user.mfa_failed_count == 0
    assert client.post(VERIFY, json={"mfa_token": token, "code": "999999"}).status_code == 422


def test_token_purposes_are_isolated(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()
    token = text_field(body_of(login(client, "admin@ibotix.ai")), "mfa_token")

    as_bearer = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert as_bearer.status_code == 401
    assert error_code(as_bearer) == "unauthenticated"

    access = create_access_token(user.id, clock.now(), settings).token
    as_mfa = client.post(SETUP, json={"mfa_token": access})
    assert as_mfa.status_code == 401
    assert error_code(as_mfa) == "unauthenticated"

    clock.advance(timedelta(minutes=5))
    expired = client.post(SETUP, json={"mfa_token": token})
    assert expired.status_code == 401


def test_employee_is_not_challenged_when_only_staff_roles_required(
    client: TestClient, db: Session, it: Department
) -> None:
    make_account(db, it, "emp@ibotix.ai", Role.EMPLOYEE)
    db.commit()
    response = login(client, "emp@ibotix.ai")
    assert response.status_code == 200
    assert set(body_of(response)) == {"access_token", "expires_in", "user"}


@pytest.fixture
def spoke_client(db: Session, clock: FrozenClock) -> Iterator[TestClient]:
    app = create_app(mfa_settings("spoke"))

    def override_db() -> Iterator[Session]:
        yield from transactional(db)

    def override_clock() -> Clock:
        return clock

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_clock] = override_clock
    with TestClient(app) as test_client:
        yield test_client


def test_spoke_mapping_triggers_enrolment(
    spoke_client: TestClient, db: Session, it: Department
) -> None:
    spoke = make_account(db, it, "spoke@ibotix.ai", Role.EMPLOYEE)
    make_spoke_assignment(db, spoke, it)
    make_account(db, it, "emp@ibotix.ai", Role.EMPLOYEE)
    make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    db.commit()

    assert body_of(login(spoke_client, "spoke@ibotix.ai"))["mfa_enrol_required"] is True
    assert "access_token" in body_of(login(spoke_client, "emp@ibotix.ai"))
    assert "access_token" in body_of(login(spoke_client, "admin@ibotix.ai"))


@pytest.fixture
def plain_client(db: Session, clock: FrozenClock) -> Iterator[TestClient]:
    app = create_app(Settings(env=Environment.TEST))

    def override_db() -> Iterator[Session]:
        yield from transactional(db)

    def override_clock() -> Clock:
        return clock

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_clock] = override_clock
    with TestClient(app) as test_client:
        yield test_client


def test_empty_required_roles_changes_nothing(
    plain_client: TestClient, db: Session, it: Department
) -> None:
    admin = make_account(db, it, "admin@ibotix.ai", Role.ADMIN)
    admin.mfa_enabled = True
    make_account(db, it, "super@ibotix.ai", Role.SUPER_ADMIN)
    spoke = make_account(db, it, "spoke@ibotix.ai", Role.EMPLOYEE)
    make_spoke_assignment(db, spoke, it)
    db.commit()

    for email in ("admin@ibotix.ai", "super@ibotix.ai", "spoke@ibotix.ai"):
        response = login(plain_client, email)
        assert response.status_code == 200
        assert set(body_of(response)) == {"access_token", "expires_in", "user"}
    for path in (SETUP, CONFIRM, VERIFY):
        response = plain_client.post(path, json={"mfa_token": "anything", "code": "123456"})
        assert response.status_code == 404
