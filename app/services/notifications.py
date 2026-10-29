import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.errors import not_found
from app.core.pagination import PageParams, fetch_page
from app.core.types import JsonObject
from app.models.identity import User
from app.models.notification import Notification
from app.models.preferences import DigestItem, NonCriticalEmail
from app.models.ticket import Ticket
from app.policy import Actor
from app.policy.visibility import visible_ticket_clause
from app.schemas.common import Page
from app.schemas.notifications import NotificationOut, UnreadCountOut
from app.services.email_outbox import enqueue_email
from app.services.preferences import email_preference
from app.services.workflow.common import status_label

CONFIDENTIAL_TEMPLATE: Final = "confidential_ticket_update"


@dataclass(frozen=True, slots=True)
class Message:
    kind: str
    text: str
    template: str | None
    context: JsonObject = field(default_factory=dict)
    critical: bool = False
    ticket_id: uuid.UUID | None = None
    dedupe_key: str | None = None


def confidential_text(ticket: Ticket) -> str:
    return f"Update on {ticket.ticket_no}"


def ticket_message(
    ticket: Ticket,
    *,
    kind: str,
    text: str,
    email: bool = True,
    extras: JsonObject | None = None,
    critical: bool = False,
    dedupe_key: str | None = None,
) -> Message:
    summary: JsonObject = {
        "ticket_id": ticket.ticket_no,
        "department": ticket.department_id,
        "status": status_label(ticket.status),
        "priority": ticket.priority.value,
    }
    if ticket.confidential:
        return Message(
            kind=kind,
            text=confidential_text(ticket),
            template=CONFIDENTIAL_TEMPLATE if email else None,
            context=summary,
            critical=critical,
            ticket_id=ticket.id,
            dedupe_key=dedupe_key,
        )
    return Message(
        kind=kind,
        text=text,
        template=kind if email else None,
        context={**summary, "title": ticket.title, "text": text, **(extras or {})},
        critical=critical,
        ticket_id=ticket.id,
        dedupe_key=dedupe_key,
    )


class Notifier:
    def __init__(self, session: Session, at: datetime) -> None:
        self._session = session
        self._at = at
        self._clock = FrozenClock(at)

    def send(self, user: User, message: Message, *, email: bool) -> uuid.UUID | None:
        statement = (
            insert(Notification)
            .values(
                id=uuid.uuid4(),
                user_id=user.id,
                ticket_id=message.ticket_id,
                kind=message.kind,
                text=message.text,
                critical=message.critical,
                dedupe_key=message.dedupe_key,
                created_at=self._at,
            )
            .on_conflict_do_nothing(
                index_elements=[Notification.user_id, Notification.dedupe_key],
                index_where=Notification.dedupe_key.is_not(None),
            )
            .returning(Notification.id)
        )
        notification_id = self._session.execute(statement).scalar_one_or_none()
        if notification_id is None:
            return None
        if not email or message.template is None:
            return notification_id
        choice = (
            NonCriticalEmail.IMMEDIATE
            if message.critical
            else email_preference(self._session, user.id).non_critical_email
        )
        if choice is NonCriticalEmail.DAILY_DIGEST:
            self._session.add(
                DigestItem(user_id=user.id, notification_id=notification_id, queued_at=self._at)
            )
            self._session.flush()
        elif choice is NonCriticalEmail.IMMEDIATE:
            enqueue_email(
                self._session,
                self._clock,
                user.email,
                message.template,
                {**message.context, "name": user.name},
                notification_id,
            )
        return notification_id


class NotificationService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def list_own(self, actor: Actor, unread: bool, params: PageParams) -> Page[NotificationOut]:
        statement = self._own(actor).order_by(
            Notification.created_at.desc(), Notification.id.desc()
        )
        if unread:
            statement = statement.where(Notification.read_at.is_(None))
        result = fetch_page(self._session, statement, params)
        numbers = self._ticket_numbers(result.items)
        return Page[NotificationOut](
            items=[
                NotificationOut(
                    id=str(item.id),
                    created_at=item.created_at,
                    read=item.read_at is not None,
                    critical=item.critical,
                    text=item.text,
                    ticket_id=numbers.get(item.ticket_id) if item.ticket_id else None,
                    kind=item.kind,
                )
                for item in result.items
            ],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def unread_count(self, actor: Actor) -> UnreadCountOut:
        own = self._own(actor).where(Notification.read_at.is_(None)).subquery()
        count = self._session.scalar(select(func.count()).select_from(own))
        return UnreadCountOut(count=count or 0)

    def mark_read(self, actor: Actor, notification_id: str) -> None:
        try:
            parsed = uuid.UUID(notification_id)
        except ValueError as exc:
            raise not_found() from exc
        notification = self._session.get(Notification, parsed)
        if notification is None or notification.user_id != actor.id:
            raise not_found()
        if notification.read_at is None:
            notification.read_at = self._clock.now()
        self._session.flush()

    def mark_all_read(self, actor: Actor) -> None:
        self._session.execute(
            update(Notification)
            .where(Notification.user_id == actor.id, Notification.read_at.is_(None))
            .values(read_at=self._clock.now())
        )

    @staticmethod
    def _own(actor: Actor) -> Select[tuple[Notification]]:
        return (
            select(Notification)
            .outerjoin(Ticket, Ticket.id == Notification.ticket_id)
            .where(
                Notification.user_id == actor.id,
                or_(Notification.ticket_id.is_(None), visible_ticket_clause(actor)),
            )
        )

    def _ticket_numbers(self, items: list[Notification]) -> dict[uuid.UUID, str]:
        ticket_ids = {item.ticket_id for item in items if item.ticket_id is not None}
        if not ticket_ids:
            return {}
        rows = self._session.execute(
            select(Ticket.id, Ticket.ticket_no).where(Ticket.id.in_(ticket_ids))
        )
        return dict(rows.tuples().all())
