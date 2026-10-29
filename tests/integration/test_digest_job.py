import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.clock import IST, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState
from app.integrations.email import InMemorySender
from app.models import (
    Department,
    DigestItem,
    EmailOutbox,
    NonCriticalEmail,
    Notification,
    NotificationDigest,
    NotificationPreference,
    Ticket,
    User,
)
from app.services.notifications import Notifier, ticket_message
from app.worker import JobContext
from app.worker.jobs import digest, registered_jobs
from tests.factories import FACTORY_NOW, make_department, make_ticket, make_user

T0 = FACTORY_NOW
DIGEST_HOUR = 11


@dataclass(frozen=True)
class Desk:
    it: Department
    user: User
    ticket: Ticket
    hidden: Ticket


@pytest.fixture
def desk(db: Session) -> Desk:
    return build_desk(db)


def build_desk(session: Session) -> Desk:
    it = make_department(session, "IT")
    hr = make_department(session, "HR")
    user = make_user(session, it, name="Rita Requester")
    ticket = make_ticket(session, user, it, title="Printer jam on floor 3")
    hidden = make_ticket(session, make_user(session, hr), hr, title="Payroll dispute")
    return Desk(it=it, user=user, ticket=ticket, hidden=hidden)


def prefer(session: Session, user: User, choice: NonCriticalEmail, hour: int = DIGEST_HOUR) -> None:
    session.add(
        NotificationPreference(
            user_id=user.id, non_critical_email=choice, digest_hour=hour, updated_at=T0
        )
    )
    session.flush()


def notify(
    session: Session,
    user: User,
    ticket: Ticket,
    text_: str,
    at: datetime = T0,
    *,
    critical: bool = False,
) -> uuid.UUID | None:
    message = ticket_message(ticket, kind="status_changed", text=text_, critical=critical)
    return Notifier(session, at).send(user, message, email=True)


def ist(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def run_at(session: Session, clock: FrozenClock, settings: Settings, at: datetime) -> int:
    clock.set(at)
    return digest.run(session, JobContext(clock=clock, settings=settings, sender=InMemorySender()))


def outbox(session: Session, template: str | None = None) -> list[EmailOutbox]:
    session.expire_all()
    statement = select(EmailOutbox).order_by(EmailOutbox.created_at, EmailOutbox.id)
    if template is not None:
        statement = statement.where(EmailOutbox.template == template)
    return list(session.scalars(statement))


def count(session: Session, model: type[DigestItem] | type[NotificationDigest]) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_default_preference_emails_immediately(db: Session, desk: Desk) -> None:
    notification_id = notify(db, desk.user, desk.ticket, "Status moved to in progress")
    [email] = outbox(db)
    assert email.template == "status_changed"
    assert email.notification_id == notification_id
    assert count(db, DigestItem) == 0


def test_daily_digest_queues_instead_of_emailing(db: Session, desk: Desk) -> None:
    prefer(db, desk.user, NonCriticalEmail.DAILY_DIGEST)
    notification_id = notify(db, desk.user, desk.ticket, "Status moved to in progress")
    assert outbox(db) == []
    item = db.scalars(select(DigestItem)).one()
    assert item.notification_id == notification_id
    assert item.queued_at == T0


def test_off_sends_no_email_but_keeps_the_portal_notification(db: Session, desk: Desk) -> None:
    prefer(db, desk.user, NonCriticalEmail.OFF)
    notify(db, desk.user, desk.ticket, "Status moved to in progress")
    assert outbox(db) == []
    assert count(db, DigestItem) == 0
    assert db.scalars(select(Notification.text)).all() == ["Status moved to in progress"]


@pytest.mark.parametrize("choice", [NonCriticalEmail.OFF, NonCriticalEmail.DAILY_DIGEST])
def test_critical_notifications_always_email(
    db: Session, desk: Desk, choice: NonCriticalEmail
) -> None:
    prefer(db, desk.user, choice)
    breach = ticket_message(
        desk.ticket,
        kind="escalation",
        text="L2 breach",
        critical=True,
        extras={"timer": "initial response", "level": 2},
    )
    Notifier(db, T0).send(desk.user, breach, email=True)
    [email] = outbox(db)
    assert email.template == "escalation"
    assert count(db, DigestItem) == 0


def test_digest_is_sent_once_per_ist_day_at_the_chosen_hour(
    db: Session, desk: Desk, clock: FrozenClock, settings: Settings
) -> None:
    prefer(db, desk.user, NonCriticalEmail.DAILY_DIGEST)
    notify(db, desk.user, desk.ticket, "First update", T0)
    notify(db, desk.user, desk.ticket, "Second update", T0 + timedelta(minutes=5))
    assert run_at(db, clock, settings, ist(27, 10, 59)) == 0
    assert run_at(db, clock, settings, ist(27, 11, 0)) == 1
    [email] = outbox(db, "notification_digest")
    assert email.to_address == desk.user.email
    assert email.notification_id is None
    assert email.body_text.index("First update") < email.body_text.index("Second update")
    assert f"/tickets/{desk.ticket.ticket_no}" in email.body_text
    assert "27 Oct 2026 (2 new)" in email.body_text
    assert run_at(db, clock, settings, ist(27, 11, 1)) == 0
    notify(db, desk.user, desk.ticket, "Third update", ist(27, 12))
    assert run_at(db, clock, settings, ist(27, 23, 59)) == 0
    assert run_at(db, clock, settings, ist(28, 10, 0)) == 0
    assert run_at(db, clock, settings, ist(28, 11, 0)) == 1
    second = outbox(db, "notification_digest")[1]
    assert "Third update" in second.body_text
    assert "First update" not in second.body_text
    assert count(db, NotificationDigest) == 2


def test_no_digest_without_queued_items(
    db: Session, desk: Desk, clock: FrozenClock, settings: Settings
) -> None:
    prefer(db, desk.user, NonCriticalEmail.DAILY_DIGEST)
    assert run_at(db, clock, settings, ist(27, 12)) == 0
    assert count(db, NotificationDigest) == 0
    assert outbox(db) == []


def test_hidden_and_confidential_tickets_never_leak(
    db: Session, desk: Desk, clock: FrozenClock, settings: Settings
) -> None:
    prefer(db, desk.user, NonCriticalEmail.DAILY_DIGEST)
    secret = make_ticket(db, desk.user, desk.it, title="Harassment complaint")
    notify(db, desk.user, desk.hidden, "Payroll dispute escalated")
    notify(db, desk.user, secret, "Harassment complaint updated")
    notify(db, desk.user, desk.ticket, "Printer fixed")
    secret.confidential = True
    db.flush()
    assert run_at(db, clock, settings, ist(27, 12)) == 1
    [email] = outbox(db, "notification_digest")
    content = email.subject + email.body_text + email.body_html
    assert "Payroll" not in content
    assert desk.hidden.ticket_no not in content
    assert "Harassment" not in content
    assert f"Update on {secret.ticket_no}" in content
    assert "Printer fixed" in content
    assert "(2 new)" in content
    dropped = db.scalars(select(DigestItem).where(DigestItem.dropped_at.is_not(None))).all()
    assert len(dropped) == 1


def test_long_digests_are_truncated(
    db: Session,
    desk: Desk,
    clock: FrozenClock,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(digest, "MAX_ITEMS", 2)
    prefer(db, desk.user, NonCriticalEmail.DAILY_DIGEST)
    for index in range(3):
        notify(db, desk.user, desk.ticket, f"Update {index}", T0 + timedelta(minutes=index))
    assert run_at(db, clock, settings, ist(27, 12)) == 1
    [email] = outbox(db, "notification_digest")
    assert "Update 1" in email.body_text
    assert "Update 2" not in email.body_text
    assert "and 1 more" in email.body_text
    assert db.scalars(select(DigestItem).where(DigestItem.sent_at.is_(None))).all() == []


def test_inactive_users_get_no_digest(
    db: Session, desk: Desk, clock: FrozenClock, settings: Settings
) -> None:
    prefer(db, desk.user, NonCriticalEmail.DAILY_DIGEST)
    notify(db, desk.user, desk.ticket, "Status moved")
    desk.user.state = AccountState.DEACTIVATED
    db.flush()
    assert run_at(db, clock, settings, ist(27, 12)) == 0
    assert outbox(db) == []
    item = db.scalars(select(DigestItem)).one()
    assert item.dropped_at is not None


def test_digest_job_runs_before_the_outbox() -> None:
    names = [job.name for job in registered_jobs()]
    assert names.index("digest") < names.index("send_outbox")


def test_two_workers_send_one_digest(
    committed_db: Session, migrated_engine: Engine, clock: FrozenClock, settings: Settings
) -> None:
    desk = build_desk(committed_db)
    prefer(committed_db, desk.user, NonCriticalEmail.DAILY_DIGEST)
    notify(committed_db, desk.user, desk.ticket, "Status moved")
    committed_db.commit()
    clock.set(ist(27, 12))
    context = JobContext(clock=clock, settings=settings, sender=InMemorySender())
    barrier = threading.Barrier(2, timeout=30)
    results: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def work() -> None:
        try:
            with Session(bind=migrated_engine, autoflush=False, expire_on_commit=False) as session:
                barrier.wait()
                outcome = digest.run(session, context)
            with lock:
                results.append(outcome)
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert errors == []
    assert sorted(results) == [0, 1]
    assert len(outbox(committed_db, "notification_digest")) == 1
    assert count(committed_db, NotificationDigest) == 1
