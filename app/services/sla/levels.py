from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models.sla import SlaTimer, TimerKind
from app.models.ticket import Ticket

SLA_TIMER_KINDS: Final = frozenset(
    {TimerKind.INITIAL_RESPONSE, TimerKind.PROGRESS_UPDATE, TimerKind.ETA}
)


def is_active(timer: SlaTimer) -> bool:
    return timer.met_at is None and timer.stopped_at is None


def is_running(timer: SlaTimer) -> bool:
    return is_active(timer) and timer.paused_at is None


def timer_level(timer: SlaTimer, now: datetime) -> int:
    if timer.kind not in SLA_TIMER_KINDS or not is_running(timer):
        return 0
    if timer.l3_at is not None and now >= timer.l3_at:
        return 3
    if now >= timer.due_at:
        return 2
    if timer.warning_at is not None and now >= timer.warning_at:
        return 1
    return 0


def ticket_timers(session: Session, ticket: Ticket) -> list[SlaTimer]:
    statement = select(SlaTimer).where(SlaTimer.ticket_id == ticket.id).order_by(SlaTimer.kind)
    return list(session.scalars(statement))


def apply_levels(ticket: Ticket, timers: list[SlaTimer], now: datetime) -> None:
    for timer in timers:
        timer.level = timer_level(timer, now)
    ticket.escalation_level = max(
        (timer.level for timer in timers if timer.kind in SLA_TIMER_KINDS), default=0
    )
    ticket.update_overdue = any(
        timer.kind is TimerKind.PROGRESS_UPDATE and timer.level >= 1 for timer in timers
    )


def recompute_ticket(session: Session, clock: Clock, ticket: Ticket) -> None:
    apply_levels(ticket, ticket_timers(session, ticket), clock.now())
    session.flush()
