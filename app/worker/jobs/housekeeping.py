import logging
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import delete, exists, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.clock import Clock
from app.integrations.storage import Storage, StorageError, build_storage
from app.models.identity import EmailToken, RateLimitHit, RefreshToken
from app.models.ticket import Attachment
from app.worker import JobContext

BATCH_SIZE: Final = 100
UNLINKED_ATTACHMENT_AGE: Final = timedelta(hours=24)
EMAIL_TOKEN_AGE: Final = timedelta(days=7)
REFRESH_TOKEN_AGE: Final = timedelta(days=30)
RATE_LIMIT_AGE: Final = timedelta(days=1)

logger = logging.getLogger("app.worker.housekeeping")


def purge_attachments(session: Session, storage: Storage, now: datetime) -> int:
    rows = list(
        session.scalars(
            select(Attachment)
            .where(
                Attachment.ticket_id.is_(None),
                Attachment.created_at < now - UNLINKED_ATTACHMENT_AGE,
            )
            .order_by(Attachment.created_at, Attachment.id)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )
    keys = [row.storage_key for row in rows]
    for row in rows:
        session.delete(row)
    session.commit()
    for key in keys:
        try:
            storage.delete(key)
        except (StorageError, OSError):
            logger.exception("could not delete a stored attachment file")
    return len(rows)


def purge_email_tokens(session: Session, now: datetime) -> int:
    cutoff = now - EMAIL_TOKEN_AGE
    deleted = session.scalars(
        delete(EmailToken)
        .where(or_(EmailToken.used_at < cutoff, EmailToken.expires_at < cutoff))
        .returning(EmailToken.id)
        .execution_options(synchronize_session=False)
    )
    return len(deleted.all())


def purge_refresh_tokens(session: Session, now: datetime) -> int:
    cutoff = now - REFRESH_TOKEN_AGE
    successor = aliased(RefreshToken)
    kept_reference = exists().where(
        successor.replaced_by_id == RefreshToken.id,
        not_(or_(successor.revoked_at < cutoff, successor.expires_at < cutoff)),
    )
    deleted = session.scalars(
        delete(RefreshToken)
        .where(
            or_(RefreshToken.revoked_at < cutoff, RefreshToken.expires_at < cutoff),
            ~kept_reference,
        )
        .returning(RefreshToken.id)
        .execution_options(synchronize_session=False)
    )
    return len(deleted.all())


def purge_rate_limits(session: Session, now: datetime) -> int:
    deleted = session.scalars(
        delete(RateLimitHit)
        .where(RateLimitHit.window_start < now - RATE_LIMIT_AGE)
        .returning(RateLimitHit.id)
        .execution_options(synchronize_session=False)
    )
    return len(deleted.all())


def housekeeping(session: Session, clock: Clock, storage: Storage) -> int:
    now = clock.now()
    removed = purge_attachments(session, storage, now)
    removed += purge_email_tokens(session, now)
    removed += purge_refresh_tokens(session, now)
    removed += purge_rate_limits(session, now)
    session.commit()
    return removed


def run(session: Session, context: JobContext) -> int:
    return housekeeping(session, context.clock, build_storage(context.settings))
