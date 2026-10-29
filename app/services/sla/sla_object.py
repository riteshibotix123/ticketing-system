from collections.abc import Iterable
from datetime import datetime
from typing import Final

from pydantic import BaseModel

from app.core.enums import SlaKind, TicketStatus
from app.models.sla import SlaTimer, TimerKind
from app.models.ticket import Ticket
from app.services.sla.levels import is_active, is_running

PAUSED_STATUSES: Final = frozenset({TicketStatus.ON_HOLD, TicketStatus.AWAITING_REQUESTER})
GOVERNING_KINDS: Final = {
    TimerKind.INITIAL_RESPONSE: SlaKind.INITIAL_RESPONSE,
    TimerKind.PROGRESS_UPDATE: SlaKind.PROGRESS_UPDATE,
    TimerKind.ETA: SlaKind.ETA,
}
LABELS: Final = {
    SlaKind.INITIAL_RESPONSE: ("Initial response due", "Initial response overdue"),
    SlaKind.PROGRESS_UPDATE: ("Next update due", "Update overdue"),
    SlaKind.ETA: ("ETA due", "ETA overdue"),
}
OVERDUE_LEVEL: Final = 2
NO_TIMER_LABEL: Final = "On track"


class SlaState(BaseModel):
    level: int
    kind: SlaKind | None
    paused: bool
    stopped: bool
    due_at: datetime | None
    label: str


def _governing(timers: Iterable[SlaTimer]) -> SlaTimer | None:
    candidates = [timer for timer in timers if timer.kind in GOVERNING_KINDS and is_running(timer)]
    if not candidates:
        return None
    return min(candidates, key=lambda timer: (-timer.level, timer.due_at))


def build_sla_state(ticket: Ticket, timers: Iterable[SlaTimer]) -> SlaState:
    timer_list = list(timers)
    if ticket.status is TicketStatus.CLOSED or ticket.status is TicketStatus.CANCELLED:
        label = "Closed" if ticket.status is TicketStatus.CLOSED else "Cancelled"
        return SlaState(level=0, kind=None, paused=False, stopped=True, due_at=None, label=label)
    if ticket.status is TicketStatus.RESOLVED:
        auto_close = next(
            (
                timer
                for timer in timer_list
                if timer.kind is TimerKind.AUTO_CLOSE and is_active(timer)
            ),
            None,
        )
        return SlaState(
            level=0,
            kind=None,
            paused=True,
            stopped=False,
            due_at=auto_close.due_at if auto_close else None,
            label="Awaiting closure",
        )
    if ticket.status in PAUSED_STATUSES:
        return SlaState(
            level=0, kind=None, paused=True, stopped=False, due_at=None, label="Timer paused"
        )
    timer = _governing(timer_list)
    if timer is None:
        return SlaState(
            level=0, kind=None, paused=False, stopped=False, due_at=None, label=NO_TIMER_LABEL
        )
    kind = GOVERNING_KINDS[timer.kind]
    due_label, overdue_label = LABELS[kind]
    return SlaState(
        level=timer.level,
        kind=kind,
        paused=False,
        stopped=False,
        due_at=timer.due_at,
        label=overdue_label if timer.level >= OVERDUE_LEVEL else due_label,
    )
