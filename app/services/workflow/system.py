import uuid
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import TicketStatus
from app.models.ticket import CloseReason, Ticket
from app.services.workflow.closure import close_ticket
from app.services.workflow.common import Workflow

AUTO_CLOSE_DETAIL: Final = "Closed automatically after the confirmation period"


def close_system(session: Session, clock: Clock, ticket_id: uuid.UUID) -> bool:
    statement = (
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ticket = session.scalars(statement).first()
    if ticket is None or ticket.status is not TicketStatus.RESOLVED:
        return False
    close_ticket(
        Workflow(session, clock), ticket, None, clock.now(), CloseReason.AUTO, AUTO_CLOSE_DETAIL
    )
    session.flush()
    return True
