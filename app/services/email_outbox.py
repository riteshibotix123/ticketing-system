import uuid

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import get_settings
from app.core.types import JsonObject
from app.models.notification import EmailOutbox, EmailStatus
from app.services.email_templates import render_email


def enqueue_email(
    session: Session,
    clock: Clock,
    to: str,
    template: str,
    context: JsonObject,
    notification_id: uuid.UUID | None = None,
) -> EmailOutbox:
    frontend_base_url = get_settings().frontend_base_url.rstrip("/")
    rendered = render_email(template, {**context, "frontend_base_url": frontend_base_url})
    now = clock.now()
    row = EmailOutbox(
        notification_id=notification_id,
        to_address=to,
        template=template,
        context=context,
        subject=rendered.subject,
        body_text=rendered.body_text,
        body_html=rendered.body_html,
        status=EmailStatus.PENDING,
        attempts=0,
        next_attempt_at=now,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row
