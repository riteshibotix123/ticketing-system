import uuid
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import TicketStatus
from app.models.sla import SlaTimer, TimerKind
from app.models.ticket import Ticket
from app.services.sla.levels import is_active
from app.services.workflow.system import close_system
from app.worker import JobContext

BATCH_SIZE: Final = 100


def due_ticket_ids(session: Session, clock: Clock) -> list[uuid.UUID]:
    statement = (
        select(SlaTimer.ticket_id)
        .join(Ticket, Ticket.id == SlaTimer.ticket_id)
        .where(
            SlaTimer.kind == TimerKind.AUTO_CLOSE,
            SlaTimer.met_at.is_(None),
            SlaTimer.stopped_at.is_(None),
            SlaTimer.due_at <= clock.now(),
            Ticket.status == TicketStatus.RESOLVED,
        )
        .order_by(SlaTimer.due_at, SlaTimer.ticket_id)
        .limit(BATCH_SIZE)
    )
    return list(session.scalars(statement))


def close_due(session: Session, clock: Clock, ticket_id: uuid.UUID) -> bool:
    ticket = session.scalars(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).first()
    if ticket is None or ticket.status is not TicketStatus.RESOLVED:
        return False
    timer = session.scalars(
        select(SlaTimer)
        .where(SlaTimer.ticket_id == ticket_id, SlaTimer.kind == TimerKind.AUTO_CLOSE)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if timer is None or not is_active(timer) or timer.due_at > clock.now():
        return False
    return close_system(session, clock, ticket_id)


def run(session: Session, context: JobContext) -> int:
    ticket_ids = due_ticket_ids(session, context.clock)
    session.commit()
    closed = 0
    for ticket_id in ticket_ids:
        if close_due(session, context.clock, ticket_id):
            closed += 1
        session.commit()
    return closed
