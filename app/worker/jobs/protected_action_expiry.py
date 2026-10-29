import uuid
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import ProtectedActionStatus
from app.models.identity import ProtectedActionRequest, User
from app.services.audit import AuditService
from app.services.handlers.notification_handlers import ACTION_VERBS, deliver
from app.services.handlers.recipients import Recipients, active_user
from app.services.notifications import Message
from app.worker import JobContext

BATCH_SIZE: Final = 100


def expired_ids(session: Session, clock: Clock) -> list[uuid.UUID]:
    statement = (
        select(ProtectedActionRequest.id)
        .where(
            ProtectedActionRequest.status == ProtectedActionStatus.PENDING,
            ProtectedActionRequest.expires_at <= clock.now(),
        )
        .order_by(ProtectedActionRequest.expires_at, ProtectedActionRequest.id)
        .limit(BATCH_SIZE)
    )
    return list(session.scalars(statement))


def expire(session: Session, clock: Clock, request_id: uuid.UUID) -> bool:
    request = session.scalars(
        select(ProtectedActionRequest)
        .where(ProtectedActionRequest.id == request_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).first()
    now = clock.now()
    if (
        request is None
        or request.status is not ProtectedActionStatus.PENDING
        or request.expires_at > now
    ):
        return False
    request.status = ProtectedActionStatus.EXPIRED
    request.updated_at = now
    AuditService(session, clock).record(
        action="protected_action_expired",
        object_type="protected_action",
        object_id=request.id,
        old_value={"status": ProtectedActionStatus.PENDING},
        new_value={"status": ProtectedActionStatus.EXPIRED},
        is_security_limited=True,
    )
    target = session.get(User, request.target_user_id)
    target_name = target.name if target is not None else "Unknown"
    verb = ACTION_VERBS[request.kind]
    recipients = Recipients().add([active_user(session, request.requested_by_id)], email=True)
    message = Message(
        kind="protected_action_decided",
        text=f"The request to {verb} Super Admin {target_name} expired",
        template="protected_action_decided",
        context={"target": target_name, "action": verb, "status": "expired"},
        critical=True,
    )
    deliver(session, now, recipients.items(), message)
    return True


def run(session: Session, context: JobContext) -> int:
    request_ids = expired_ids(session, context.clock)
    session.commit()
    expired = 0
    for request_id in request_ids:
        if expire(session, context.clock, request_id):
            expired += 1
        session.commit()
    return expired
