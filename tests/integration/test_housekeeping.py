import io
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.enums import ProtectedActionStatus, Role
from app.integrations.email import InMemorySender
from app.integrations.storage import LocalStorage
from app.models import (
    Attachment,
    AuditLog,
    Department,
    EmailToken,
    Notification,
    ProtectedActionRequest,
    RateLimitHit,
    RefreshToken,
    User,
)
from app.services.handlers import register_all
from app.worker import JobContext
from app.worker.jobs import housekeeping, protected_action_expiry
from tests.factories import (
    make_attachment,
    make_department,
    make_email_token,
    make_protected_action,
    make_rate_limit_hit,
    make_refresh_token,
    make_ticket,
    make_user,
)


@pytest.fixture(autouse=True)
def handlers() -> None:
    register_all()


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT")


@pytest.fixture
def user(db: Session, it: Department) -> User:
    return make_user(db, it)


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "files")


def test_unlinked_old_attachments_are_deleted_with_files(
    db: Session, clock: FrozenClock, it: Department, user: User, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path / "files")
    ticket = make_ticket(db, user, it)
    rows: dict[str, Attachment] = {}
    for name, age, linked in (
        ("old", timedelta(hours=25), False),
        ("recent", timedelta(hours=23), False),
        ("linked", timedelta(days=3), True),
    ):
        key = storage.save(io.BytesIO(b"hello"), "attachments")
        row = make_attachment(db, user, ticket=ticket if linked else None, at=clock.now() - age)
        row.storage_key = key
        rows[name] = row
    db.flush()
    housekeeping.housekeeping(db, clock, storage)
    remaining = set(db.scalars(select(Attachment.id)))
    assert remaining == {rows["recent"].id, rows["linked"].id}
    files = {path.name for path in (tmp_path / "files" / "attachments").iterdir()}
    assert files == {
        rows["recent"].storage_key.split("/")[1],
        rows["linked"].storage_key.split("/")[1],
    }


def test_tokens_and_rate_limits(
    db: Session, clock: FrozenClock, user: User, storage: LocalStorage
) -> None:
    now = clock.now()
    days = timedelta(days=1)
    used_old = make_email_token(db, user, at=now - 9 * days)
    used_old.used_at = now - 8 * days
    used_recent = make_email_token(db, user, at=now - 7 * days)
    used_recent.used_at = now - 6 * days
    make_email_token(db, user, at=now - 9 * days, lifetime=days)
    live = make_email_token(db, user, at=now - 30 * days, lifetime=60 * days)
    revoked_old = make_refresh_token(db, user, at=now - 40 * days, lifetime=60 * days)
    revoked_old.revoked_at = now - 31 * days
    revoked_recent = make_refresh_token(db, user, at=now - 40 * days, lifetime=60 * days)
    revoked_recent.revoked_at = now - 29 * days
    make_refresh_token(db, user, at=now - 40 * days)
    successor_old = make_refresh_token(db, user, at=now - 45 * days)
    kept_parent = make_refresh_token(db, user, at=now - 5 * days)
    kept_parent.revoked_at = now - 5 * days
    kept_parent.replaced_by_id = successor_old.id
    active = make_refresh_token(db, user, at=now)
    make_rate_limit_hit(db, "login:a", window_start=now - timedelta(hours=25))
    recent_hit = make_rate_limit_hit(db, "login:b", window_start=now - timedelta(hours=23))
    db.flush()
    removed = housekeeping.housekeeping(db, clock, storage)
    db.expire_all()
    assert set(db.scalars(select(EmailToken.id))) == {used_recent.id, live.id}
    assert set(db.scalars(select(RefreshToken.id))) == {
        revoked_recent.id,
        successor_old.id,
        kept_parent.id,
        active.id,
    }
    assert set(db.scalars(select(RateLimitHit.id))) == {recent_hit.id}
    assert removed == 2 + 2 + 1


@pytest.fixture
def context(clock: FrozenClock, settings: Settings) -> JobContext:
    return JobContext(clock=clock, settings=settings, sender=InMemorySender())


def test_protected_action_expiry(
    db: Session, clock: FrozenClock, context: JobContext, it: Department
) -> None:
    requester = make_user(db, it, role=Role.SUPER_ADMIN, name="Sue Super")
    target = make_user(db, it, role=Role.SUPER_ADMIN, name="Tom Target")
    expired = make_protected_action(db, target, requester, at=clock.now() - timedelta(hours=73))
    pending = make_protected_action(db, target, requester, at=clock.now() - timedelta(hours=71))
    db.commit()
    assert protected_action_expiry.run(db, context) == 1
    assert protected_action_expiry.run(db, context) == 0
    db.expire_all()
    stored = db.get(ProtectedActionRequest, expired.id)
    untouched = db.get(ProtectedActionRequest, pending.id)
    assert stored is not None
    assert untouched is not None
    assert stored.status is ProtectedActionStatus.EXPIRED
    assert untouched.status is ProtectedActionStatus.PENDING
    [entry] = db.scalars(select(AuditLog).where(AuditLog.action == "protected_action_expired"))
    assert entry.object_id == str(expired.id)
    assert entry.is_security_limited is True
    assert entry.actor_id is None
    [note] = db.scalars(select(Notification).where(Notification.kind == "protected_action_decided"))
    assert note.user_id == requester.id
    assert note.critical is True
    assert note.text == "The request to deactivate Super Admin Tom Target expired"
