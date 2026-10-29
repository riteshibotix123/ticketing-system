import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock, to_ist
from app.core.types import JsonObject
from app.models.identity import User
from app.models.notification import Notification
from app.models.preferences import (
    DigestItem,
    NonCriticalEmail,
    NotificationDigest,
    NotificationPreference,
)
from app.models.ticket import Ticket
from app.policy import Actor
from app.policy.actors import load_actor
from app.policy.visibility import visible_ticket_clause
from app.services.email_outbox import enqueue_email
from app.services.notifications import confidential_text
from app.worker import JobContext

DIGEST_TEMPLATE: Final = "notification_digest"
MAX_ITEMS: Final = 50
BATCH_SIZE: Final = 100
DATE_FORMAT: Final = "%d %b %Y"


def due_users(session: Session, now: datetime) -> list[uuid.UUID]:
    local = to_ist(now)
    pending = exists().where(
        DigestItem.user_id == NotificationPreference.user_id,
        DigestItem.sent_at.is_(None),
        DigestItem.dropped_at.is_(None),
    )
    sent_today = exists().where(
        NotificationDigest.user_id == NotificationPreference.user_id,
        NotificationDigest.digest_date == local.date(),
    )
    statement = (
        select(NotificationPreference.user_id)
        .where(
            NotificationPreference.non_critical_email == NonCriticalEmail.DAILY_DIGEST,
            NotificationPreference.digest_hour <= local.hour,
            pending,
            ~sent_today,
        )
        .order_by(NotificationPreference.user_id)
        .limit(BATCH_SIZE)
    )
    return list(session.scalars(statement))


def visible_tickets(
    session: Session, actor: Actor, ticket_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Ticket]:
    if not ticket_ids:
        return {}
    statement = select(Ticket).where(Ticket.id.in_(ticket_ids), visible_ticket_clause(actor))
    return {ticket.id: ticket for ticket in session.scalars(statement)}


def item_entry(notification: Notification, ticket: Ticket | None) -> JsonObject:
    if ticket is None:
        return {"text": notification.text, "ticket_id": None}
    text = confidential_text(ticket) if ticket.confidential else notification.text
    return {"text": text, "ticket_id": ticket.ticket_no}


def send_digest(session: Session, clock: Clock, user_id: uuid.UUID) -> bool:
    now = clock.now()
    rows = session.execute(
        select(DigestItem, Notification)
        .join(Notification, Notification.id == DigestItem.notification_id)
        .where(
            DigestItem.user_id == user_id,
            DigestItem.sent_at.is_(None),
            DigestItem.dropped_at.is_(None),
        )
        .order_by(DigestItem.queued_at, DigestItem.id)
        .with_for_update(of=DigestItem, skip_locked=True)
    ).all()
    if not rows:
        return False
    actor = load_actor(session, user_id)
    user = session.get(User, user_id)
    if actor is None or user is None:
        for item, _ in rows:
            item.dropped_at = now
        session.flush()
        return False
    tickets = visible_tickets(
        session,
        actor,
        {notification.ticket_id for _, notification in rows if notification.ticket_id},
    )
    kept: list[tuple[DigestItem, Notification]] = []
    for item, notification in rows:
        if notification.ticket_id is not None and notification.ticket_id not in tickets:
            item.dropped_at = now
        else:
            kept.append((item, notification))
    session.flush()
    if not kept:
        return False
    today = to_ist(now).date()
    digest_id = session.execute(
        insert(NotificationDigest)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            digest_date=today,
            item_count=len(kept),
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "digest_date"])
        .returning(NotificationDigest.id)
    ).scalar_one_or_none()
    if digest_id is None:
        return False
    for item, _ in kept:
        item.sent_at = now
        item.digest_id = digest_id
    entries: list[JsonObject] = [
        item_entry(
            notification,
            tickets.get(notification.ticket_id) if notification.ticket_id else None,
        )
        for _, notification in kept[:MAX_ITEMS]
    ]
    enqueue_email(
        session,
        clock,
        user.email,
        DIGEST_TEMPLATE,
        {
            "name": user.name,
            "date": today.strftime(DATE_FORMAT),
            "count": len(kept),
            "items": list(entries),
            "more": max(0, len(kept) - MAX_ITEMS),
        },
    )
    return True


def run(session: Session, context: JobContext) -> int:
    user_ids = due_users(session, context.clock.now())
    session.commit()
    sent = 0
    for user_id in user_ids:
        if send_digest(session, context.clock, user_id):
            sent += 1
        session.commit()
    return sent
