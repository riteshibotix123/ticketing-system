from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.integrations.email import EmailSender, OutgoingEmail
from app.models.notification import EmailOutbox, EmailStatus
from app.worker import JobContext

BATCH_SIZE = 20
MAX_ATTEMPTS = 5
MAX_ERROR_LENGTH = 1000
BACKOFF = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(minutes=120),
)


def send_outbox(session: Session, clock: Clock, sender: EmailSender) -> int:
    now = clock.now()
    rows = session.scalars(
        select(EmailOutbox)
        .where(EmailOutbox.status == EmailStatus.PENDING, EmailOutbox.next_attempt_at <= now)
        .order_by(EmailOutbox.next_attempt_at, EmailOutbox.created_at)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        _deliver(row, sender, now)
    session.commit()
    return len(rows)


def run(session: Session, context: JobContext) -> int:
    return send_outbox(session, context.clock, context.sender)


def _deliver(row: EmailOutbox, sender: EmailSender, now: datetime) -> None:
    message = OutgoingEmail(
        to_address=row.to_address,
        subject=row.subject,
        body_text=row.body_text,
        body_html=row.body_html,
    )
    try:
        sender.send(message)
    except Exception as exc:
        _record_failure(row, exc, now)
        return
    row.status = EmailStatus.SENT
    row.sent_at = now
    row.last_error = None


def _record_failure(row: EmailOutbox, exc: Exception, now: datetime) -> None:
    row.attempts += 1
    row.last_error = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
    if row.attempts >= MAX_ATTEMPTS:
        row.status = EmailStatus.FAILED
        return
    row.next_attempt_at = now + BACKOFF[row.attempts - 1]
