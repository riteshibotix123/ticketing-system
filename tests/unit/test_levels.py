import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import Priority, SlaKind, TicketStatus
from app.models import SlaTimer, Ticket, TimerKind
from app.services.sla.levels import apply_levels, timer_level
from app.services.sla.sla_object import build_sla_state

START = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)


def make_timer(
    kind: TimerKind = TimerKind.INITIAL_RESPONSE,
    *,
    warning: float | None = 18,
    due: float = 24,
    l3: float | None = 48,
    level: int = 0,
    paused: bool = False,
    met: bool = False,
    stopped: bool = False,
) -> SlaTimer:
    return SlaTimer(
        ticket_id=uuid.uuid4(),
        kind=kind,
        cycle=1,
        started_at=START,
        warning_at=START + timedelta(hours=warning) if warning is not None else None,
        due_at=START + timedelta(hours=due),
        l3_at=START + timedelta(hours=l3) if l3 is not None else None,
        paused_at=START if paused else None,
        paused_seconds=0,
        level=level,
        met_at=START if met else None,
        stopped_at=START if stopped else None,
    )


def make_ticket(status: TicketStatus = TicketStatus.NEW) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        status=status,
        priority=Priority.MEDIUM,
        escalation_level=0,
        update_overdue=False,
    )


@pytest.mark.parametrize(
    ("hours", "expected"),
    [(0, 0), (17.99, 0), (18, 1), (23.99, 1), (24, 2), (47.99, 2), (48, 3), (100, 3)],
)
def test_timer_level_thresholds(hours: float, expected: int) -> None:
    assert timer_level(make_timer(), START + timedelta(hours=hours)) == expected


@pytest.mark.parametrize(
    ("warning", "l3", "hours", "expected"),
    [
        (12, 30, 11.9, 0),
        (12, 30, 12, 1),
        (12, 30, 24, 2),
        (12, 30, 30, 3),
        (18, 36, 17.9, 0),
        (18, 36, 35.9, 2),
        (18, 36, 36, 3),
    ],
)
def test_timer_level_per_priority_thresholds(
    warning: float, l3: float, hours: float, expected: int
) -> None:
    timer = make_timer(warning=warning, l3=l3)
    assert timer_level(timer, START + timedelta(hours=hours)) == expected


@pytest.mark.parametrize(
    "timer",
    [
        make_timer(paused=True),
        make_timer(met=True),
        make_timer(stopped=True),
        make_timer(TimerKind.AUTO_CLOSE, warning=None, l3=None),
        make_timer(TimerKind.REQUESTER_REMINDER, warning=None, l3=None),
        make_timer(TimerKind.HOLD_REVIEW, warning=None, l3=None),
    ],
    ids=["paused", "met", "stopped", "auto_close", "requester_reminder", "hold_review"],
)
def test_inactive_and_non_sla_timers_have_level_zero(timer: SlaTimer) -> None:
    assert timer_level(timer, START + timedelta(days=30)) == 0


def test_apply_levels_sets_ticket_maximum_and_update_overdue() -> None:
    ticket = make_ticket(TicketStatus.IN_PROGRESS)
    progress = make_timer(TimerKind.PROGRESS_UPDATE, warning=20, due=24, l3=48)
    eta = make_timer(TimerKind.ETA, warning=1, due=2, l3=26)
    auto_close = make_timer(TimerKind.AUTO_CLOSE, warning=None, due=1, l3=None)
    apply_levels(ticket, [progress, eta, auto_close], START + timedelta(hours=21))
    assert (progress.level, eta.level, auto_close.level) == (1, 2, 0)
    assert ticket.escalation_level == 2
    assert ticket.update_overdue is True
    apply_levels(ticket, [progress], START + timedelta(hours=1))
    assert ticket.escalation_level == 0
    assert ticket.update_overdue is False


def test_sla_state_closed_and_cancelled() -> None:
    closed = build_sla_state(make_ticket(TicketStatus.CLOSED), [make_timer(level=3)])
    assert closed.model_dump() == {
        "level": 0,
        "kind": None,
        "paused": False,
        "stopped": True,
        "due_at": None,
        "label": "Closed",
    }
    cancelled = build_sla_state(make_ticket(TicketStatus.CANCELLED), [])
    assert cancelled.label == "Cancelled"
    assert cancelled.stopped is True


def test_sla_state_resolved_uses_auto_close_due() -> None:
    auto_close = make_timer(TimerKind.AUTO_CLOSE, warning=None, due=72, l3=None)
    state = build_sla_state(make_ticket(TicketStatus.RESOLVED), [auto_close])
    assert (state.level, state.kind, state.paused, state.stopped) == (0, None, True, False)
    assert state.due_at == auto_close.due_at
    assert state.label == "Awaiting closure"
    assert build_sla_state(make_ticket(TicketStatus.RESOLVED), []).due_at is None


@pytest.mark.parametrize("status", [TicketStatus.ON_HOLD, TicketStatus.AWAITING_REQUESTER])
def test_sla_state_paused_statuses(status: TicketStatus) -> None:
    state = build_sla_state(make_ticket(status), [make_timer(TimerKind.ETA, level=2)])
    assert state.model_dump() == {
        "level": 0,
        "kind": None,
        "paused": True,
        "stopped": False,
        "due_at": None,
        "label": "Timer paused",
    }


@pytest.mark.parametrize(
    ("kind", "level", "label"),
    [
        (TimerKind.INITIAL_RESPONSE, 0, "Initial response due"),
        (TimerKind.INITIAL_RESPONSE, 1, "Initial response due"),
        (TimerKind.INITIAL_RESPONSE, 2, "Initial response overdue"),
        (TimerKind.PROGRESS_UPDATE, 1, "Next update due"),
        (TimerKind.PROGRESS_UPDATE, 3, "Update overdue"),
        (TimerKind.ETA, 0, "ETA due"),
        (TimerKind.ETA, 2, "ETA overdue"),
    ],
)
def test_sla_state_labels(kind: TimerKind, level: int, label: str) -> None:
    timer = make_timer(kind, level=level)
    state = build_sla_state(make_ticket(TicketStatus.IN_PROGRESS), [timer])
    assert state.kind == SlaKind(kind.value)
    assert state.level == level
    assert state.label == label
    assert state.due_at == timer.due_at


def test_sla_state_governing_timer_highest_level_then_earliest_due() -> None:
    progress = make_timer(TimerKind.PROGRESS_UPDATE, due=24, level=1)
    eta = make_timer(TimerKind.ETA, due=10, level=1)
    met = make_timer(TimerKind.INITIAL_RESPONSE, due=5, level=3, met=True)
    state = build_sla_state(make_ticket(TicketStatus.IN_PROGRESS), [progress, eta, met])
    assert state.kind is SlaKind.ETA
    eta.level = 0
    state = build_sla_state(make_ticket(TicketStatus.IN_PROGRESS), [progress, eta, met])
    assert state.kind is SlaKind.PROGRESS_UPDATE


@pytest.mark.parametrize(
    "status",
    [
        TicketStatus.NEW,
        TicketStatus.ACKNOWLEDGED,
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.REOPENED,
    ],
)
def test_sla_state_active_statuses_use_governing_timer(status: TicketStatus) -> None:
    state = build_sla_state(make_ticket(status), [make_timer(level=1)])
    assert (state.kind, state.paused, state.stopped) == (SlaKind.INITIAL_RESPONSE, False, False)
