import threading
from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import get_settings
from app.integrations.email import InMemorySender, OutgoingEmail
from app.models import EmailOutbox, EmailStatus
from app.services.email_outbox import enqueue_email
from app.worker.jobs.send_outbox import BACKOFF, BATCH_SIZE, MAX_ATTEMPTS, send_outbox
from tests.factories import make_department, make_notification, make_outbox_email, make_user


def status_of(db: Session, row: EmailOutbox) -> EmailStatus:
    db.refresh(row)
    return row.status


class FailingSender:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.sent: list[OutgoingEmail] = []

    def send(self, message: OutgoingEmail) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionRefusedError("smtp unavailable")
        self.sent.append(message)


class SlowSender(InMemorySender):
    def send(self, message: OutgoingEmail) -> None:
        threading.Event().wait(0.01)
        super().send(message)


def test_enqueue_renders_and_writes_pending_row(
    db: Session, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://helpdesk.ibotix.ai/")
    get_settings.cache_clear()
    user = make_user(db, make_department(db, "IT"))
    notification = make_notification(db, user)

    row = enqueue_email(
        db,
        clock,
        "asha@ibotix.ai",
        "password_reset",
        {"name": "Asha", "token": "tok-1", "expires_minutes": 60},
        notification_id=notification.id,
    )

    stored = db.get(EmailOutbox, row.id)
    assert stored is not None
    assert stored.status is EmailStatus.PENDING
    assert stored.attempts == 0
    assert stored.notification_id == notification.id
    assert stored.to_address == "asha@ibotix.ai"
    assert stored.template == "password_reset"
    assert stored.context == {"name": "Asha", "token": "tok-1", "expires_minutes": 60}
    assert stored.subject == "Reset your password"
    assert "https://helpdesk.ibotix.ai/reset-password?token=tok-1" in stored.body_text
    assert "https://helpdesk.ibotix.ai/reset-password?token=tok-1" in stored.body_html
    assert stored.next_attempt_at == clock.now()
    assert stored.created_at == clock.now()
    assert stored.sent_at is None


def test_send_success_marks_sent(db: Session, clock: FrozenClock) -> None:
    row = make_outbox_email(db, "a@ibotix.ai", at=clock.now())
    sender = InMemorySender()

    assert send_outbox(db, clock, sender) == 1

    assert status_of(db, row) is EmailStatus.SENT
    assert row.sent_at == clock.now()
    assert row.attempts == 0
    assert sender.sent == [
        OutgoingEmail(
            to_address="a@ibotix.ai", subject="Subject", body_text="Body", body_html="<p>Body</p>"
        )
    ]
    assert send_outbox(db, clock, sender) == 0
    assert len(sender.sent) == 1


def test_rows_not_yet_due_are_skipped(db: Session, clock: FrozenClock) -> None:
    make_outbox_email(db, "later@ibotix.ai", at=clock.now() + timedelta(seconds=1))
    sender = InMemorySender()

    assert send_outbox(db, clock, sender) == 0
    assert sender.sent == []


def test_batch_is_limited(db: Session, clock: FrozenClock) -> None:
    for index in range(BATCH_SIZE + 3):
        make_outbox_email(db, f"user{index}@ibotix.ai", at=clock.now())
    sender = InMemorySender()

    assert send_outbox(db, clock, sender) == BATCH_SIZE
    assert send_outbox(db, clock, sender) == 3
    assert len(sender.sent) == BATCH_SIZE + 3


def test_failure_retries_with_backoff_then_succeeds(db: Session, clock: FrozenClock) -> None:
    row = make_outbox_email(db, "a@ibotix.ai", at=clock.now())
    sender = FailingSender(failures=2)
    start = clock.now()

    assert send_outbox(db, clock, sender) == 1
    assert status_of(db, row) is EmailStatus.PENDING
    assert row.attempts == 1
    assert row.last_error == "ConnectionRefusedError: smtp unavailable"
    assert row.next_attempt_at == start + timedelta(minutes=1)

    clock.advance(timedelta(seconds=59))
    assert send_outbox(db, clock, sender) == 0

    clock.advance(timedelta(seconds=1))
    assert send_outbox(db, clock, sender) == 1
    db.refresh(row)
    assert row.attempts == 2
    assert row.next_attempt_at == clock.now() + timedelta(minutes=5)

    clock.advance(timedelta(minutes=5))
    assert send_outbox(db, clock, sender) == 1
    assert status_of(db, row) is EmailStatus.SENT
    assert row.sent_at == clock.now()
    assert row.last_error is None
    assert row.attempts == 2
    assert len(sender.sent) == 1


def test_final_failure_after_max_attempts(db: Session, clock: FrozenClock) -> None:
    row = make_outbox_email(db, "a@ibotix.ai", at=clock.now())
    sender = FailingSender(failures=MAX_ATTEMPTS + 1)
    observed: list[timedelta] = []

    for _ in range(MAX_ATTEMPTS - 1):
        assert send_outbox(db, clock, sender) == 1
        assert status_of(db, row) is EmailStatus.PENDING
        observed.append(row.next_attempt_at - clock.now())
        clock.set(row.next_attempt_at)

    assert observed == list(BACKOFF)
    assert send_outbox(db, clock, sender) == 1
    assert status_of(db, row) is EmailStatus.FAILED
    assert row.attempts == MAX_ATTEMPTS
    assert row.sent_at is None
    assert row.last_error == "ConnectionRefusedError: smtp unavailable"

    clock.advance(timedelta(days=1))
    assert send_outbox(db, clock, sender) == 0
    assert sender.sent == []


def test_two_concurrent_workers_never_send_a_row_twice(
    committed_db: Session, migrated_engine: Engine, clock: FrozenClock
) -> None:
    total = BATCH_SIZE * 3
    for index in range(total):
        make_outbox_email(committed_db, f"user{index}@ibotix.ai", at=clock.now())
    committed_db.commit()
    sender = SlowSender()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def work() -> None:
        try:
            with Session(bind=migrated_engine, expire_on_commit=False) as session:
                barrier.wait()
                while send_outbox(session, clock, sender) > 0:
                    pass
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    counts = Counter(message.to_address for message in sender.sent)
    assert len(counts) == total
    assert set(counts.values()) == {1}
    committed_db.expire_all()
    statuses = committed_db.scalars(select(EmailOutbox.status)).all()
    assert statuses == [EmailStatus.SENT] * total
