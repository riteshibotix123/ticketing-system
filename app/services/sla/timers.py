from datetime import datetime, timedelta
from typing import Final

from sqlalchemy.orm import Session

from app.core.enums import TicketStatus
from app.models.sla import SlaTimer, TimerKind
from app.models.ticket import Ticket
from app.services.calendar import load_working_calendar, ticket_sla_mode
from app.services.policy import PolicyConfig
from app.services.sla.due_time import (
    SlaModeName,
    add_business_days,
    calculate_due,
    scaled_hours,
)
from app.services.sla.levels import is_active, ticket_timers
from app.services.sla.working_time import WorkingCalendar

TERMINAL_STATUSES: Final = frozenset({TicketStatus.CLOSED, TicketStatus.CANCELLED})
PAUSABLE_KINDS: Final = (TimerKind.PROGRESS_UPDATE, TimerKind.ETA)


class Timers:
    def __init__(
        self, session: Session, ticket: Ticket, policy: PolicyConfig, scale: float
    ) -> None:
        self._session = session
        self._ticket = ticket
        self._policy = policy
        self._scale = scale
        self._timers = {timer.kind: timer for timer in ticket_timers(session, ticket)}
        self._mode: SlaModeName | None = None
        self._calendar: WorkingCalendar | None = None

    @property
    def all(self) -> list[SlaTimer]:
        return [self._timers[kind] for kind in TimerKind if kind in self._timers]

    def get(self, kind: TimerKind) -> SlaTimer | None:
        return self._timers.get(kind)

    def _hours(self, hours: float) -> timedelta:
        return scaled_hours(hours, self._scale)

    @property
    def mode(self) -> SlaModeName:
        if self._mode is None:
            self._mode = ticket_sla_mode(self._session, self._ticket, self._policy.sla_mode)
        return self._mode

    @property
    def calendar(self) -> WorkingCalendar:
        if self._calendar is None:
            self._calendar = load_working_calendar(self._session)
        return self._calendar

    def _due(self, start: datetime, hours: float) -> datetime:
        if self.mode == "business":
            return calculate_due(start, hours, "business", self._scale, self.calendar)
        return calculate_due(start, hours, "calendar", self._scale)

    def start(
        self,
        kind: TimerKind,
        now: datetime,
        due_at: datetime,
        warning_at: datetime | None = None,
        l3_at: datetime | None = None,
    ) -> SlaTimer:
        timer = self._timers.get(kind)
        if timer is not None:
            return self.restart(kind, now, due_at, warning_at, l3_at)
        timer = SlaTimer(
            ticket_id=self._ticket.id,
            kind=kind,
            cycle=1,
            started_at=now,
            warning_at=warning_at,
            due_at=due_at,
            l3_at=l3_at,
            paused_seconds=0,
            level=0,
        )
        self._session.add(timer)
        self._timers[kind] = timer
        return timer

    def restart(
        self,
        kind: TimerKind,
        now: datetime,
        due_at: datetime,
        warning_at: datetime | None = None,
        l3_at: datetime | None = None,
    ) -> SlaTimer:
        timer = self._timers.get(kind)
        if timer is None:
            return self.start(kind, now, due_at, warning_at, l3_at)
        timer.cycle += 1
        timer.started_at = now
        timer.warning_at = warning_at
        timer.due_at = due_at
        timer.l3_at = l3_at
        timer.paused_at = None
        timer.paused_seconds = 0
        timer.level = 0
        timer.met_at = None
        timer.stopped_at = None
        return timer

    def pause(self, kind: TimerKind, now: datetime) -> None:
        timer = self._timers.get(kind)
        if timer is not None and is_active(timer) and timer.paused_at is None:
            timer.paused_at = now

    def resume(self, kind: TimerKind, now: datetime) -> None:
        timer = self._timers.get(kind)
        if timer is None or timer.paused_at is None or not is_active(timer):
            return
        timer.paused_seconds += max(0, int((now - timer.paused_at).total_seconds()))
        timer.paused_at = None

    def mark_met(self, kind: TimerKind, now: datetime) -> None:
        timer = self._timers.get(kind)
        if timer is not None and is_active(timer):
            if timer.paused_at is not None:
                self.resume(kind, now)
            timer.met_at = now

    def stop(self, kind: TimerKind, now: datetime) -> None:
        timer = self._timers.get(kind)
        if timer is not None and is_active(timer):
            if timer.paused_at is not None:
                self.resume(kind, now)
            timer.stopped_at = now

    def stop_all(self, now: datetime) -> None:
        for kind in TimerKind:
            self.stop(kind, now)

    def is_active(self, kind: TimerKind) -> bool:
        timer = self._timers.get(kind)
        return timer is not None and is_active(timer)

    def start_initial_response(self, start: datetime) -> SlaTimer:
        priority = self._ticket.priority
        return self.start(
            TimerKind.INITIAL_RESPONSE,
            start,
            due_at=self._due(start, self._policy.initial_response_hours),
            warning_at=self._due(start, self._policy.warning_hours[priority]),
            l3_at=self._due(start, self._policy.l3_hours[priority]),
        )

    def start_progress_update(self, start: datetime) -> SlaTimer:
        cadence = self._policy.update_cadence_hours
        return self.start(
            TimerKind.PROGRESS_UPDATE,
            start,
            due_at=self._due(start, cadence),
            warning_at=self._due(start, self._policy.update_warning_hours),
            l3_at=self._due(start, 2 * cadence),
        )

    def eta_due(self) -> datetime | None:
        if self._ticket.eta is not None:
            return self._ticket.eta
        return self._ticket.next_checkpoint_at

    def start_eta(self, now: datetime) -> SlaTimer | None:
        due = self.eta_due()
        if due is None:
            self.stop(TimerKind.ETA, now)
            return None
        return self.start(
            TimerKind.ETA,
            now,
            due_at=due,
            warning_at=due - self._hours(self._policy.eta_warning_hours),
            l3_at=self._due(due, self._policy.update_cadence_hours),
        )

    def start_requester_reminder(self, start: datetime) -> SlaTimer:
        return self.start(
            TimerKind.REQUESTER_REMINDER,
            start,
            due_at=self._due(start, self._policy.requester_reminder_hours),
        )

    def start_hold_review(self, now: datetime) -> SlaTimer | None:
        review = self._ticket.hold_review_date
        if review is None:
            self.stop(TimerKind.HOLD_REVIEW, now)
            return None
        return self.start(TimerKind.HOLD_REVIEW, now, due_at=review)

    def start_auto_close(self, start: datetime) -> SlaTimer | None:
        days = self._policy.auto_close_business_days
        if days is None:
            self.stop(TimerKind.AUTO_CLOSE, start)
            return None
        return self.start(
            TimerKind.AUTO_CLOSE, start, due_at=add_business_days(start, days, self.calendar)
        )

    def recompute_initial_response_thresholds(self) -> None:
        timer = self._timers.get(TimerKind.INITIAL_RESPONSE)
        if timer is None or not is_active(timer):
            return
        priority = self._ticket.priority
        timer.warning_at = self._due(timer.started_at, self._policy.warning_hours[priority])
        timer.l3_at = self._due(timer.started_at, self._policy.l3_hours[priority])

    def reconcile(self, now: datetime) -> None:
        status = self._ticket.status
        if status in TERMINAL_STATUSES:
            self.stop_all(now)
            return
        if status is TicketStatus.NEW or status is TicketStatus.REOPENED:
            self._reconcile_unacknowledged(status, now)
            return
        if status is TicketStatus.RESOLVED:
            self._reconcile_resolved(now)
            return
        self._reconcile_working(status, now)

    def _reconcile_unacknowledged(self, status: TicketStatus, now: datetime) -> None:
        if self.get(TimerKind.INITIAL_RESPONSE) is None or (
            status is TicketStatus.NEW and not self.is_active(TimerKind.INITIAL_RESPONSE)
        ):
            self.start_initial_response(self._ticket.sla_started_at)
        for kind in (
            TimerKind.PROGRESS_UPDATE,
            TimerKind.ETA,
            TimerKind.REQUESTER_REMINDER,
            TimerKind.HOLD_REVIEW,
            TimerKind.AUTO_CLOSE,
        ):
            self.stop(kind, now)

    def _reconcile_resolved(self, now: datetime) -> None:
        self.mark_met(TimerKind.INITIAL_RESPONSE, now)
        self.mark_met(TimerKind.ETA, now)
        for kind in (
            TimerKind.PROGRESS_UPDATE,
            TimerKind.REQUESTER_REMINDER,
            TimerKind.HOLD_REVIEW,
        ):
            self.stop(kind, now)
        if self._policy.auto_close_business_days is None:
            self.stop(TimerKind.AUTO_CLOSE, now)
        elif not self.is_active(TimerKind.AUTO_CLOSE):
            self.start_auto_close(self._ticket.resolved_at or now)

    def _reconcile_working(self, status: TicketStatus, now: datetime) -> None:
        self.mark_met(TimerKind.INITIAL_RESPONSE, now)
        self.stop(TimerKind.AUTO_CLOSE, now)
        if not self.is_active(TimerKind.PROGRESS_UPDATE):
            self.start_progress_update(
                self._ticket.last_team_update_at or self._ticket.acknowledged_at or now
            )
        if self.get(TimerKind.ETA) is None:
            self.start_eta(self._ticket.acknowledged_at or now)
        if status is TicketStatus.AWAITING_REQUESTER:
            for kind in PAUSABLE_KINDS:
                self.pause(kind, now)
            self.stop(TimerKind.HOLD_REVIEW, now)
            if not self.is_active(TimerKind.REQUESTER_REMINDER):
                self.start_requester_reminder(self._ticket.awaiting_since or now)
            return
        if status is TicketStatus.ON_HOLD:
            for kind in PAUSABLE_KINDS:
                self.pause(kind, now)
            self.stop(TimerKind.REQUESTER_REMINDER, now)
            if not self.is_active(TimerKind.HOLD_REVIEW):
                self.start_hold_review(now)
            return
        for kind in PAUSABLE_KINDS:
            self.resume(kind, now)
        self.stop(TimerKind.REQUESTER_REMINDER, now)
        self.stop(TimerKind.HOLD_REVIEW, now)
