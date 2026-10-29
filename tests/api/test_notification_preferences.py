import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.security import create_access_token
from app.models import AuditLog, Department, NonCriticalEmail, NotificationPreference, User
from tests.factories import make_department, make_user

PREFERENCES = "/api/v1/me/notification-preferences"
DEFAULTS = {"non_critical_email": "immediate", "digest_hour": 9, "critical_email": "always"}


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def test_defaults_then_save_own_preferences(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = make_user(db, it)
    other = make_user(db, it)
    headers = bearer(db, user, clock, settings)
    assert client.get(PREFERENCES, headers=headers).json() == DEFAULTS
    saved = client.put(
        PREFERENCES,
        json={"non_critical_email": "daily_digest", "digest_hour": 18},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    expected = {"non_critical_email": "daily_digest", "digest_hour": 18, "critical_email": "always"}
    assert saved.json() == expected
    assert client.get(PREFERENCES, headers=headers).json() == expected
    muted = client.put(
        PREFERENCES, json={"non_critical_email": "off", "digest_hour": 0}, headers=headers
    )
    assert muted.json()["non_critical_email"] == "off"
    db.expire_all()
    row = db.get(NotificationPreference, user.id)
    assert row is not None
    assert row.non_critical_email is NonCriticalEmail.OFF
    assert row.digest_hour == 0
    assert db.get(NotificationPreference, other.id) is None
    other_view = client.get(PREFERENCES, headers=bearer(db, other, clock, settings))
    assert other_view.json() == DEFAULTS
    assert db.scalars(select(AuditLog)).all() == []


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"non_critical_email": "weekly", "digest_hour": 9}, "non_critical_email"),
        ({"non_critical_email": "off", "digest_hour": 24}, "digest_hour"),
        ({"non_critical_email": "off", "digest_hour": -1}, "digest_hour"),
        ({"non_critical_email": "off", "digest_hour": "9"}, "digest_hour"),
        ({"non_critical_email": "off", "digest_hour": 9.5}, "digest_hour"),
        ({"non_critical_email": "off"}, "digest_hour"),
        (
            {"non_critical_email": "off", "digest_hour": 9, "critical_email": "never"},
            "critical_email",
        ),
        (
            {"non_critical_email": "off", "digest_hour": 9, "critical_email": "always"},
            "critical_email",
        ),
    ],
)
def test_invalid_preferences(
    client: TestClient,
    db: Session,
    it: Department,
    clock: FrozenClock,
    settings: Settings,
    body: dict[str, object],
    field: str,
) -> None:
    user = make_user(db, it)
    response = client.put(PREFERENCES, json=body, headers=bearer(db, user, clock, settings))
    assert response.status_code == 422, response.text
    assert field in response.json()["error"]["fields"]
    assert db.get(NotificationPreference, user.id) is None


def test_anonymous_callers_get_401(client: TestClient) -> None:
    assert client.get(PREFERENCES).status_code == 401
    assert client.put(PREFERENCES, json={}).status_code == 401
