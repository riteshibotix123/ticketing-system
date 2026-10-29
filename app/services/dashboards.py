import uuid
from typing import Final

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import SignupStatus, TicketStatus
from app.core.errors import forbidden
from app.models.identity import SignupRequest, User
from app.models.ticket import Ticket, TicketEvent
from app.policy import Actor
from app.policy.flags import TICKETS_VIEW_ALL, TICKETS_VIEW_DEPARTMENT, has_permission
from app.policy.permissions import can_decide_signup
from app.policy.visibility import visible_ticket_clause
from app.queries.tickets import apply_sort, in_departments, is_active_ticket, visible_tickets
from app.schemas.common import SYSTEM_ACTOR, SystemActor, UserRef
from app.schemas.dashboards import AdminDashboardOut, EmployeeDashboardOut, SpokeDashboardOut
from app.schemas.tickets import TicketOut, TimelineEventOut
from app.services.kpis import KpiService
from app.services.policy import PolicyService
from app.services.spokes import user_ref
from app.services.ticket_reads import TicketPresenter

ATTENTION_LIMIT: Final = 6
RECENT_UPDATES_LIMIT: Final = 10
URGENCY: Final = "urgency"


class DashboardService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._presenter = TicketPresenter(session, clock)

    def employee(self, actor: Actor) -> EmployeeDashboardOut:
        requested = Ticket.requester_id == actor.id
        assigned = Ticket.assignee_id == actor.id
        involved = or_(requested, assigned)
        return EmployeeDashboardOut(
            open=self._count(actor, requested, is_active_ticket()),
            awaiting_my_response=self._count(
                actor, requested, Ticket.status == TicketStatus.AWAITING_REQUESTER
            ),
            resolved_to_confirm=self._count(
                actor, requested, Ticket.status == TicketStatus.RESOLVED
            ),
            closed=self._count(actor, requested, Ticket.status == TicketStatus.CLOSED),
            assigned_to_me=self._count(actor, assigned, is_active_ticket()),
            assigned_warning=self._count(
                actor, assigned, is_active_ticket(), Ticket.escalation_level == 1
            ),
            assigned_breached=self._count(
                actor, assigned, is_active_ticket(), Ticket.escalation_level >= 2
            ),
            recent_updates=self._recent_updates(actor, involved),
            attention=self._attention(
                actor,
                involved,
                or_(
                    Ticket.escalation_level > 0,
                    Ticket.status == TicketStatus.AWAITING_REQUESTER,
                ),
            ),
        )

    def spoke(self, actor: Actor) -> SpokeDashboardOut:
        if not self._allowed(actor, TICKETS_VIEW_DEPARTMENT):
            raise forbidden()
        scope = in_departments(actor.spoke_department_ids)
        now = self._clock.now()
        overdue_eta = and_(is_active_ticket(), Ticket.eta.is_not(None), Ticket.eta < now)
        kpis = KpiService(self._session, self._clock).dashboard(actor, actor.spoke_department_ids)
        return SpokeDashboardOut(
            new_unacknowledged=self._count(actor, scope, Ticket.status == TicketStatus.NEW),
            approaching_sla=self._count(
                actor, scope, is_active_ticket(), Ticket.escalation_level == 1
            ),
            breached=self._count(actor, scope, Ticket.escalation_level >= 2),
            stale_or_eta_overdue=self._count(
                actor, scope, or_(Ticket.update_overdue.is_(True), overdue_eta)
            ),
            awaiting_requester=self._count(
                actor, scope, Ticket.status == TicketStatus.AWAITING_REQUESTER
            ),
            on_hold=self._count(actor, scope, Ticket.status == TicketStatus.ON_HOLD),
            resolved_pending_closure=self._count(
                actor, scope, Ticket.status == TicketStatus.RESOLVED
            ),
            sla_met_pct=kpis.sla_met_pct,
            avg_initial_response_seconds=kpis.avg_initial_response_seconds,
            reopen_rate_pct=kpis.reopen_rate_pct,
            by_department=kpis.by_department,
            attention=self._attention(actor, scope, is_active_ticket()),
        )

    def admin(self, actor: Actor) -> AdminDashboardOut:
        if not self._allowed(actor, TICKETS_VIEW_ALL):
            raise forbidden()
        kpis = KpiService(self._session, self._clock).dashboard(actor, None)
        return AdminDashboardOut(
            open_count=self._count(actor, is_active_ticket()),
            breached_count=self._count(actor, Ticket.escalation_level >= 2),
            l3_count=self._count(actor, Ticket.escalation_level == 3),
            stale_count=self._count(actor, Ticket.update_overdue.is_(True)),
            pending_approvals=self._pending_approvals(actor),
            sla_met_pct=kpis.sla_met_pct,
            avg_initial_response_seconds=kpis.avg_initial_response_seconds,
            reopen_rate_pct=kpis.reopen_rate_pct,
            by_department=kpis.by_department,
            attention=self._attention(actor, is_active_ticket()),
        )

    def _allowed(self, actor: Actor, flag: str) -> bool:
        policy = PolicyService(self._session).current()
        return has_permission(actor, flag, policy.admins_can_manage_departments)

    def _count(self, actor: Actor, *clauses: ColumnElement[bool]) -> int:
        statement = (
            select(func.count()).select_from(Ticket).where(visible_ticket_clause(actor), *clauses)
        )
        return self._session.scalar(statement) or 0

    def _attention(self, actor: Actor, *clauses: ColumnElement[bool]) -> list[TicketOut]:
        statement = apply_sort(visible_tickets(actor).where(*clauses), URGENCY).limit(
            ATTENTION_LIMIT
        )
        return self._presenter.present(actor, list(self._session.scalars(statement)))

    def _recent_updates(
        self, actor: Actor, involved: ColumnElement[bool]
    ) -> list[TimelineEventOut]:
        statement = (
            select(TicketEvent)
            .join(Ticket, Ticket.id == TicketEvent.ticket_id)
            .where(visible_ticket_clause(actor), involved, TicketEvent.is_public.is_(True))
            .order_by(TicketEvent.at.desc(), TicketEvent.id.desc())
            .limit(RECENT_UPDATES_LIMIT)
        )
        events = list(self._session.scalars(statement))
        users = self._users({event.actor_id for event in events if event.actor_id is not None})
        return [self._event_out(event, users) for event in events]

    def _users(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not user_ids:
            return {}
        rows = self._session.scalars(select(User).where(User.id.in_(user_ids)))
        return {user.id: user for user in rows}

    @staticmethod
    def _event_out(event: TicketEvent, users: dict[uuid.UUID, User]) -> TimelineEventOut:
        author: UserRef | SystemActor = (
            user_ref(users[event.actor_id])
            if event.actor_id is not None and event.actor_id in users
            else SYSTEM_ACTOR
        )
        return TimelineEventOut(
            id=str(event.id),
            at=event.at,
            actor=author,
            type=event.kind,
            action=event.action,
            detail=event.public_detail if event.public_detail is not None else event.detail,
            body=event.body,
            public=event.is_public,
        )

    def _pending_approvals(self, actor: Actor) -> int:
        rows = self._session.execute(
            select(SignupRequest.requested_role, SignupRequest.user_id)
            .join(User, User.id == SignupRequest.user_id)
            .where(
                SignupRequest.status == SignupStatus.PENDING,
                User.email_verified_at.is_not(None),
            )
        )
        return sum(
            1
            for requested_role, applicant_id in rows
            if can_decide_signup(actor, requested_role, None, applicant_id)
        )
