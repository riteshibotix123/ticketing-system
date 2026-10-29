from collections.abc import Iterator

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock, get_clock
from app.core.config import Environment, Settings
from app.core.db import get_db, transactional
from app.main import create_app
from tests.scenarios.helpers import PASSWORD, Org, Portal

LOGIN = "/api/v1/auth/login"


def login(client: TestClient, key: str) -> dict[str, object]:
    response = client.post(LOGIN, json={"email": f"{key}@ibotix.ai", "password": PASSWORD})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


@pytest.fixture
def mfa_client(db: Session, clock: FrozenClock, org: Org) -> Iterator[TestClient]:
    assert org.users
    settings = Settings(
        env=Environment.TEST,
        mfa_required_roles=["admin", "super_admin"],
        field_encryption_key=SecretStr(Fernet.generate_key().decode()),
    )
    app = create_app(settings)

    def override_db() -> Iterator[Session]:
        yield from transactional(db)

    def override_clock() -> Clock:
        return clock

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_clock] = override_clock
    with TestClient(app) as test_client:
        yield test_client


def test_nobody_is_asked_when_mfa_roles_are_empty(portal: Portal) -> None:
    for key in ("asha", "neha", "priya", "karan"):
        assert set(login(portal.client, key)) == {"access_token", "expires_in", "user"}


def test_admin_must_enrol_when_mfa_roles_are_set(
    mfa_client: TestClient, clock: FrozenClock
) -> None:
    assert set(login(mfa_client, "asha")) == {"access_token", "expires_in", "user"}
    assert set(login(mfa_client, "neha")) == {"access_token", "expires_in", "user"}
    challenge = login(mfa_client, "priya")
    assert challenge["mfa_enrol_required"] is True
    token = challenge["mfa_token"]
    assert login(mfa_client, "karan")["mfa_enrol_required"] is True

    setup = mfa_client.post("/api/v1/auth/mfa/setup", json={"mfa_token": token})
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).at(clock.now())
    confirmed = mfa_client.post("/api/v1/auth/mfa/confirm", json={"mfa_token": token, "code": code})
    assert confirmed.status_code == 200
    assert len(confirmed.json()["recovery_codes"]) == 8

    again = login(mfa_client, "priya")
    assert again["mfa_required"] is True
    verified = mfa_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": again["mfa_token"], "code": pyotp.TOTP(secret).at(clock.now())},
    )
    assert verified.status_code == 200
    assert verified.json()["user"]["mfa_enabled"] is True
