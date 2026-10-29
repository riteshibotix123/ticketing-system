import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.clock import Clock, to_ist
from app.core.enums import Priority
from app.core.errors import forbidden, validation_error
from app.models.identity import User
from app.models.org import Department
from app.models.ticket import Ticket
from app.policy import Actor
from app.policy.reports import can_view_reports, report_scope
from app.policy.visibility import visible_ticket_clause
from app.queries.kpis import (
    AGING_BUCKETS,
    RESOLVED,
    Scope,
    Window,
    department_statement,
    departments_statement,
    duration_statement,
    escalation_statement,
    eta_breach_statement,
    persistent_l3_statement,
    reopen_statement,
    scope_clauses,
    sla_statement,
    snapshot_statement,
    top_categories_statement,
    trend_statement,
    workload_statement,
)
from app.schemas.dashboards import DepartmentHealthOut
from app.schemas.reports import (
    AgingOut,
    CategoryCountOut,
    DepartmentKpiOut,
    DurationOut,
    EscalationCountsOut,
    KpiFiltersOut,
    KpiReportOut,
    PriorityCountsOut,
    ReopenOut,
    SlaComplianceOut,
    TrendPointOut,
    WorkloadOut,
    WorkloadRowOut,
)
from app.services.policy import PolicyService
from app.services.spokes import user_ref

DEFAULT_WINDOW: Final = timedelta(days=30)
MAX_WINDOW: Final = timedelta(days=366)
ONE_DAY: Final = timedelta(days=1)
JUST_BEFORE: Final = timedelta(microseconds=1)


@dataclass(frozen=True, slots=True)
class KpiQuery:
    start: datetime | None = None
    end: datetime | None = None
    department_id: str | None = None
    priorities: Sequence[Priority] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DashboardKpis:
    sla_met_pct: float | None
    avg_initial_response_seconds: int | None
    reopen_rate_pct: float | None
    by_department: list[DepartmentHealthOut]


def percent(part: int, whole: int) -> float | None:
    if whole == 0:
        return None
    return round(part * 100 / whole, 1)


def whole_seconds(value: float | None) -> int | None:
    return None if value is None else round(value)


class KpiService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def report(self, actor: Actor, query: KpiQuery) -> KpiReportOut:
        admins_manage = PolicyService(self._session).current().admins_can_manage_departments
        if not can_view_reports(actor, admins_manage):
            raise forbidden()
        now = self._clock.now()
        window = self._window(query, now)
        department_id = self._known_department(query.department_id)
        scope = report_scope(actor, admins_manage, department_id)
        if scope is None:
            raise forbidden()
        priorities = frozenset(query.priorities)
        clauses = scope_clauses(visible_ticket_clause(actor), scope.department_ids, priorities)
        departments = self._department_names(scope.department_ids, department_id)
        sla_met, sla_missed, sla_by_department = self._sla(clauses, window)
        resolved, reopened = self._reopen(clauses, window)
        initial_response, trend = self._initial_response(clauses, window)
        stale, overdue_eta, unacknowledged, *aging = self._session.execute(
            snapshot_statement(clauses, now)
        ).one()
        return KpiReportOut(
            generated_at=now,
            filters=KpiFiltersOut(
                from_=window.start,
                to=window.end,
                department_ids=sorted(
                    scope.department_ids if scope.department_ids is not None else departments
                ),
                priorities=sorted(priorities),
            ),
            sla_compliance=SlaComplianceOut(
                met=sla_met, missed=sla_missed, pct=percent(sla_met, sla_met + sla_missed)
            ),
            initial_response=initial_response,
            initial_response_trend=trend,
            resolution_turnaround=self._duration(clauses, RESOLVED, window),
            reopen=ReopenOut(
                resolved=resolved, reopened=reopened, rate_pct=percent(reopened, resolved)
            ),
            escalations=self._escalations(clauses, window),
            eta_breach_count=self._session.scalar(eta_breach_statement(clauses, window)) or 0,
            stale_count=stale,
            overdue_eta_count=overdue_eta,
            unacknowledged_over_24h=unacknowledged,
            persistent_l3_count=self._session.scalar(persistent_l3_statement(clauses)) or 0,
            aging=[
                AgingOut(bucket=bucket, count=count)
                for (bucket, _, _), count in zip(AGING_BUCKETS, aging, strict=True)
            ],
            departments=self._departments(clauses, departments, sla_by_department),
            workload=WorkloadOut(
                by_assignee=self._workload(clauses, Ticket.assignee_id),
                by_owner=self._workload(clauses, Ticket.owner_id),
            ),
            top_categories=self._top_categories(clauses, window),
        )

    def dashboard(self, actor: Actor, department_ids: frozenset[str] | None) -> DashboardKpis:
        now = self._clock.now()
        window = Window(now - DEFAULT_WINDOW, now)
        clauses = scope_clauses(visible_ticket_clause(actor), department_ids, ())
        met, missed, _ = self._sla(clauses, window)
        resolved, reopened = self._reopen(clauses, window)
        departments = self._department_names(department_ids, None)
        return DashboardKpis(
            sla_met_pct=percent(met, met + missed),
            avg_initial_response_seconds=self._initial_response(clauses, window)[0].avg_seconds,
            reopen_rate_pct=percent(reopened, resolved),
            by_department=[
                DepartmentHealthOut(
                    department_id=row.department_id,
                    name=row.name,
                    on_track=row.on_track,
                    warning=row.warning,
                    breached=row.breached,
                )
                for row in self._departments(clauses, departments, {})
            ],
        )

    def _window(self, query: KpiQuery, now: datetime) -> Window:
        end = query.end.astimezone(UTC) if query.end is not None else now
        start = query.start.astimezone(UTC) if query.start is not None else end - DEFAULT_WINDOW
        if start >= end:
            raise validation_error({"to": "Must be after from"})
        if end - start > MAX_WINDOW:
            raise validation_error({"from": "The range must be at most 366 days"})
        return Window(start, end)

    def _known_department(self, department_id: str | None) -> str | None:
        if department_id is None:
            return None
        if self._session.get(Department, department_id) is None:
            raise validation_error({"department_id": "Unknown department"})
        return department_id

    def _department_names(
        self, department_ids: Collection[str] | None, requested: str | None
    ) -> dict[str, str]:
        rows = self._session.execute(departments_statement(department_ids, requested))
        return dict(rows.tuples().all())

    def _sla(self, clauses: Scope, window: Window) -> tuple[int, int, dict[str, float | None]]:
        rows = list(self._session.execute(sla_statement(clauses, window)))
        met = sum(row_met for _, _, row_met in rows)
        missed = sum(row_missed for _, row_missed, _ in rows)
        by_department = {
            department_id: percent(row_met, row_met + row_missed)
            for department_id, row_missed, row_met in rows
        }
        return met, missed, by_department

    def _reopen(self, clauses: Scope, window: Window) -> tuple[int, int]:
        resolved, reopened = self._session.execute(reopen_statement(clauses, window)).one()
        return resolved, reopened

    def _duration(self, clauses: Scope, action: str, window: Window) -> DurationOut:
        count, average, median = self._session.execute(
            duration_statement(clauses, action, window)
        ).one()
        return DurationOut(
            count=count, avg_seconds=whole_seconds(average), median_seconds=whole_seconds(median)
        )

    def _initial_response(
        self, clauses: Scope, window: Window
    ) -> tuple[DurationOut, list[TrendPointOut]]:
        total = DurationOut(count=0, avg_seconds=None, median_seconds=None)
        days: dict[date, tuple[int, float | None]] = {}
        for is_total, day, count, average, median in self._session.execute(
            trend_statement(clauses, window)
        ):
            if is_total or day is None:
                total = DurationOut(
                    count=count,
                    avg_seconds=whole_seconds(average),
                    median_seconds=whole_seconds(median),
                )
            else:
                days[day] = (count, average)
        points: list[TrendPointOut] = []
        day = to_ist(window.start).date()
        last = to_ist(window.end - JUST_BEFORE).date()
        while day <= last:
            count, average = days.get(day, (0, None))
            points.append(
                TrendPointOut(date=day.isoformat(), count=count, avg_seconds=whole_seconds(average))
            )
            day += ONE_DAY
        return total, points

    def _escalations(self, clauses: Scope, window: Window) -> EscalationCountsOut:
        counts = dict(self._session.execute(escalation_statement(clauses, window)).tuples().all())
        return EscalationCountsOut(l1=counts.get(1, 0), l2=counts.get(2, 0), l3=counts.get(3, 0))

    def _departments(
        self,
        clauses: Scope,
        names: dict[str, str],
        sla_by_department: dict[str, float | None],
    ) -> list[DepartmentKpiOut]:
        counts = {row[0]: row[1:] for row in self._session.execute(department_statement(clauses))}
        result: list[DepartmentKpiOut] = []
        for department_id, name in names.items():
            active, low, medium, high, critical, on_track, warning, breached = counts.get(
                department_id, (0, 0, 0, 0, 0, 0, 0, 0)
            )
            result.append(
                DepartmentKpiOut(
                    department_id=department_id,
                    name=name,
                    active=active,
                    by_priority=PriorityCountsOut(
                        low=low, medium=medium, high=high, critical=critical
                    ),
                    on_track=on_track,
                    warning=warning,
                    breached=breached,
                    sla_met_pct=sla_by_department.get(department_id),
                )
            )
        return result

    def _workload(
        self, clauses: Scope, column: InstrumentedAttribute[uuid.UUID | None]
    ) -> list[WorkloadRowOut]:
        rows = list(self._session.execute(workload_statement(clauses, column)))
        user_ids = {user_id for user_id, _, _ in rows if user_id is not None}
        users = (
            {
                user.id: user
                for user in self._session.scalars(select(User).where(User.id.in_(user_ids)))
            }
            if user_ids
            else {}
        )
        named = sorted(
            (
                (users[user_id], active, breached)
                for user_id, active, breached in rows
                if user_id is not None and user_id in users
            ),
            key=lambda item: (-item[1], item[0].name, str(item[0].id)),
        )
        result = [
            WorkloadRowOut(user=user_ref(user), active=active, breached=breached)
            for user, active, breached in named
        ]
        result.extend(
            WorkloadRowOut(user=None, active=active, breached=breached)
            for user_id, active, breached in rows
            if user_id is None
        )
        return result

    def _top_categories(self, clauses: Scope, window: Window) -> list[CategoryCountOut]:
        return [
            CategoryCountOut(
                category_id=str(category_id) if category_id is not None else None,
                name=name,
                count=count,
            )
            for category_id, name, count in self._session.execute(
                top_categories_statement(clauses, window)
            )
        ]
