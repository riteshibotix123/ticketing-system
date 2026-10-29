import dataclasses
import uuid
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, to_ist
from app.core.errors import forbidden, validation_error
from app.core.pagination import parse_sort
from app.models.identity import User
from app.models.org import Category
from app.models.sla import SlaTimer
from app.models.ticket import Ticket
from app.policy import Actor
from app.policy.reports import can_view_reports, report_scope
from app.policy.visibility import visible_ticket_clause
from app.queries.kpis import scope_clauses
from app.queries.tickets import DEFAULT_SORT, SORTS, in_departments, ticket_list_statement
from app.schemas.exports import ExportFormat, ExportType
from app.services.audit import AuditService, format_utc
from app.services.exports.tables import Document, build_document, kpi_tables, ticket_table
from app.services.exports.writers import MEDIA_TYPES, render
from app.services.kpis import KpiQuery, KpiService
from app.services.policy import PolicyService
from app.services.ticket_reads import TicketListQuery, TicketReadService

ROW_LIMITS: Final = {ExportFormat.CSV: 50_000, ExportFormat.XLSX: 50_000, ExportFormat.PDF: 2_000}
CHUNK: Final = 1_000
REPORT_NAMES: Final = {ExportType.TICKETS: "Tickets", ExportType.KPIS: "KPIs"}


@dataclass(frozen=True, slots=True)
class ExportFile:
    filename: str
    media_type: str
    chunks: Iterator[bytes]


def _chunks[T](items: Sequence[T]) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), CHUNK):
        yield items[start : start + CHUNK]


def ticket_filter_values(query: TicketListQuery, sort: str) -> dict[str, str]:
    values: dict[str, str] = {"scope": query.scope.value, "sort": sort}
    optional: dict[str, object] = {
        "q": query.q.strip() if query.q and query.q.strip() else None,
        "status": ",".join(query.statuses) if query.statuses else None,
        "priority": ",".join(sorted(priority.value for priority in query.priorities))
        if query.priorities
        else None,
        "department_id": query.department_id,
        "category_id": query.category_id,
        "sla_state": query.sla_state.value if query.sla_state else None,
        "escalation_level": query.escalation_level,
        "requester_id": query.requester_id,
        "assignee_id": query.assignee_id,
        "confidential": query.confidential,
        "overdue_eta": query.overdue_eta or None,
        "unassigned": query.unassigned or None,
        "awaiting_before": query.awaiting_before,
        "created_from": query.created_from,
        "created_to": query.created_to,
    }
    for key, value in optional.items():
        if value is None:
            continue
        if isinstance(value, bool):
            values[key] = "true" if value else "false"
        elif isinstance(value, datetime):
            values[key] = format_utc(value)
        else:
            values[key] = str(value)
    return values


class ExportService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def export(
        self,
        actor: Actor,
        export_type: ExportType,
        export_format: ExportFormat,
        query: TicketListQuery,
        start: datetime | None,
        end: datetime | None,
    ) -> ExportFile:
        admins_manage = PolicyService(self._session).current().admins_can_manage_departments
        if not can_view_reports(actor, admins_manage):
            raise forbidden()
        now = self._clock.now()
        if export_type is ExportType.TICKETS:
            document, filters, confidential = self._tickets(
                actor, query, export_format, admins_manage, now
            )
        else:
            document, filters, confidential = self._kpis(
                actor, query, start, end, admins_manage, now
            )
        rows = sum(len(table.rows) for table in document.tables)
        AuditService(self._session, self._clock).record(
            action="report_exported",
            object_type="report",
            actor_id=actor.id,
            new_value={
                "type": export_type.value,
                "format": export_format.value,
                "filters": filters,
                "row_count": rows,
            },
            is_security_limited=confidential,
        )
        return ExportFile(
            filename=f"ibotix-{export_type.value}-{to_ist(now):%Y%m%d-%H%M}.{export_format.value}",
            media_type=MEDIA_TYPES[export_format],
            chunks=render(document, export_format),
        )

    def _tickets(
        self,
        actor: Actor,
        query: TicketListQuery,
        export_format: ExportFormat,
        admins_manage: bool,
        now: datetime,
    ) -> tuple[Document, dict[str, str], bool]:
        department_id = query.department_id.strip() if query.department_id else None
        scope = report_scope(actor, admins_manage, department_id or None)
        if scope is None:
            raise forbidden()
        sort = parse_sort(query.sort, SORTS, DEFAULT_SORT)
        filters = TicketReadService(self._session, self._clock).filters(actor, query)
        if scope.department_ids is not None:
            filters = dataclasses.replace(
                filters, extra=(*filters.extra, in_departments(scope.department_ids))
            )
        statement = ticket_list_statement(actor, filters, sort, now)
        total = self._session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        limit = ROW_LIMITS[export_format]
        if (total or 0) > limit:
            raise validation_error(
                {
                    "format": f"{export_format.value.upper()} exports hold at most {limit} "
                    "tickets; narrow the filters"
                }
            )
        tickets = list(self._session.scalars(statement))
        table = ticket_table(
            tickets, self._users(tickets), self._categories(tickets), self._timers(tickets)
        )
        values = ticket_filter_values(query, sort)
        document = build_document(
            REPORT_NAMES[ExportType.TICKETS], self._generated_by(actor), now, values, [table]
        )
        return document, values, any(ticket.confidential for ticket in tickets)

    def _kpis(
        self,
        actor: Actor,
        query: TicketListQuery,
        start: datetime | None,
        end: datetime | None,
        admins_manage: bool,
        now: datetime,
    ) -> tuple[Document, dict[str, str], bool]:
        kpi_query = KpiQuery(
            start=start, end=end, department_id=query.department_id, priorities=query.priorities
        )
        report = KpiService(self._session, self._clock).report(actor, kpi_query)
        values = {
            "from": format_utc(report.filters.from_),
            "to": format_utc(report.filters.to),
            "department_ids": ",".join(report.filters.department_ids),
            "priorities": ",".join(priority.value for priority in report.filters.priorities),
        }
        document = build_document(
            REPORT_NAMES[ExportType.KPIS],
            self._generated_by(actor),
            now,
            values,
            kpi_tables(report),
        )
        scope = report_scope(actor, admins_manage, query.department_id)
        department_ids = scope.department_ids if scope is not None else frozenset()
        confidential = self._session.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(
                *scope_clauses(visible_ticket_clause(actor), department_ids, query.priorities),
                Ticket.confidential.is_(True),
            )
        )
        return document, values, bool(confidential)

    @staticmethod
    def _generated_by(actor: Actor) -> str:
        return f"{actor.name} <{actor.email}>"

    def _users(self, tickets: Sequence[Ticket]) -> dict[uuid.UUID, User]:
        user_ids = sorted(
            {
                user_id
                for ticket in tickets
                for user_id in (ticket.requester_id, ticket.owner_id, ticket.assignee_id)
                if user_id is not None
            }
        )
        users: dict[uuid.UUID, User] = {}
        for chunk in _chunks(user_ids):
            users.update(
                (user.id, user)
                for user in self._session.scalars(select(User).where(User.id.in_(chunk)))
            )
        return users

    def _categories(self, tickets: Sequence[Ticket]) -> dict[uuid.UUID, Category]:
        category_ids = sorted({ticket.category_id for ticket in tickets if ticket.category_id})
        categories: dict[uuid.UUID, Category] = {}
        for chunk in _chunks(category_ids):
            categories.update(
                (category.id, category)
                for category in self._session.scalars(
                    select(Category).where(Category.id.in_(chunk))
                )
            )
        return categories

    def _timers(self, tickets: Sequence[Ticket]) -> dict[uuid.UUID, list[SlaTimer]]:
        grouped: defaultdict[uuid.UUID, list[SlaTimer]] = defaultdict(list)
        for chunk in _chunks([ticket.id for ticket in tickets]):
            for timer in self._session.scalars(
                select(SlaTimer).where(SlaTimer.ticket_id.in_(chunk))
            ):
                grouped[timer.ticket_id].append(timer)
        return grouped
