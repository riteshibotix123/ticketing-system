import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import TicketStatus
from app.models.sla import EscalationEvent, SlaTimer, TimerKind
from app.models.ticket import Ticket
from app.services.handlers.notification_handlers import deliver
from app.services.handlers.recipients import Recipients, active_user, visible_only
from app.services.notifications import ticket_message
from app.services.sla.escalation import record_step
from app.services.sla.levels import is_active
from app.worker import JobContext

BATCH_SIZE: Final = 100


@dataclass(frozen=True, slots=True)
class Reminder:
    status: TicketStatus
    step_key: str
    kind: str


REMINDERS: Final[Mapping[TimerKind, Reminder]] = MappingProxyType(
    {
        TimerKind.REQUESTER_REMINDER: Reminder(
            TicketStatus.AWAITING_REQUESTER, "REMINDER", "requester_reminder"
        ),
        TimerKind.HOLD_REVIEW: Reminder(TicketStatus.ON_HOLD, "HOLD_REVIEW", "hold_review_due"),
    }
)


def due_reminders(session: Session, clock: Clock) -> list[tuple[uuid.UUID, TimerKind]]:
    found: list[tuple[uuid.UUID, TimerKind]] = []
    for kind, reminder in REMINDERS.items():
        sent = exists().where(
            EscalationEvent.ticket_id == SlaTimer.ticket_id,
            EscalationEvent.timer_kind == SlaTimer.kind,
            EscalationEvent.cycle == SlaTimer.cycle,
            EscalationEvent.step_key == reminder.step_key,
        )
        statement = (
            select(SlaTimer.ticket_id)
            .join(Ticket, Ticket.id == SlaTimer.ticket_id)
            .where(
                SlaTimer.kind == kind,
                SlaTimer.met_at.is_(None),
                SlaTimer.stopped_at.is_(None),
                SlaTimer.due_at <= clock.now(),
                Ticket.status == reminder.status,
                ~sent,
            )
            .order_by(SlaTimer.due_at, SlaTimer.ticket_id)
            .limit(BATCH_SIZE)
        )
        found.extend((ticket_id, kind) for ticket_id in session.scalars(statement))
    return found


def send_reminder(session: Session, clock: Clock, ticket_id: uuid.UUID, kind: TimerKind) -> bool:
    reminder = REMINDERS[kind]
    ticket = session.scalars(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).first()
    if ticket is None or ticket.status is not reminder.status:
        return False
    timer = session.scalars(
        select(SlaTimer)
        .where(SlaTimer.ticket_id == ticket_id, SlaTimer.kind == kind)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    now = clock.now()
    if timer is None or not is_active(timer) or timer.due_at > now:
        return False
    user_id = ticket.requester_id if kind is TimerKind.REQUESTER_REMINDER else ticket.owner_id
    recipients = Recipients().add([active_user(session, user_id)], email=True)
    entries = visible_only(session, ticket, recipients.items())
    recorded = record_step(
        session,
        ticket,
        kind,
        timer.cycle,
        1,
        reminder.step_key,
        now,
        [entry.user.id for entry in entries],
    )
    if not recorded:
        return False
    text = (
        f"Ticket {ticket.ticket_no} is waiting for your reply"
        if kind is TimerKind.REQUESTER_REMINDER
        else f"Hold review due on {ticket.ticket_no}"
    )
    message = ticket_message(
        ticket,
        kind=reminder.kind,
        text=text,
        dedupe_key=f"{reminder.kind}:{ticket.id}:{timer.cycle}",
    )
    deliver(session, now, entries, message)
    return True


def run(session: Session, context: JobContext) -> int:
    due = due_reminders(session, context.clock)
    session.commit()
    sent = 0
    for ticket_id, kind in due:
        if send_reminder(session, context.clock, ticket_id, kind):
            sent += 1
        session.commit()
    return sent
