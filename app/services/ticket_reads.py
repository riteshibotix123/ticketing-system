import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import Priority, TicketStatus
from app.core.errors import forbidden, not_found, validation_error
from app.core.pagination import PageParams, fetch_page, parse_sort
from app.models.identity import User
from app.models.org import Category, ConfidentialGrant
from app.models.sla import SlaTimer
from app.models.ticket import Attachment, Ticket, TicketCollaborator, TicketEvent
from app.policy import Actor
from app.policy.allowed_actions import ActorClass, actor_classes, compute_allowed_actions
from app.policy.flags import TICKETS_VIEW_ALL, has_permission
from app.policy.relationships import ActorContext, contact_departments, relationship_from
from app.queries.tickets import (
    DEFAULT_SORT,
    SORTS,
    TicketFilters,
    assigned_clause,
    in_departments,
    mine_clause,
    ticket_list_statement,
    visible_ticket_by_number,
)
from app.schemas.common import SYSTEM_ACTOR, Page, SystemActor, UserRef
from app.schemas.tickets import (
    OPEN_STATUS,
    AttachmentOut,
    FeedbackOut,
    HoldOut,
    SlaStateFilter,
    TicketOut,
    TicketScope,
    TimelineEventOut,
)
from app.services.policy import PolicyConfig, PolicyService
from app.services.sla.sla_object import build_sla_state
from app.services.spokes import user_ref

STAFF_CLASSES = frozenset({ActorClass.TEAM, ActorClass.ASSIGNEE})
OPEN_STATUSES = frozenset(TicketStatus) - {
    TicketStatus.RESOLVED,
    TicketStatus.CLOSED,
    TicketStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class TicketListQuery:
    scope: TicketScope = TicketScope.MINE
    q: str | None = None
    statuses: Sequence[str] = ()
    priorities: Sequence[Priority] = ()
    department_id: str | None = None
    category_id: str | None = None
    sla_state: SlaStateFilter | None = None
    escalation_level: int | None = None
    requester_id: str | None = None
    assignee_id: str | None = None
    confidential: bool | None = None
    overdue_eta: bool = False
    unassigned: bool = False
    awaiting_before: datetime | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    sort: str | None = None


def parse_statuses(values: Iterable[str]) -> frozenset[TicketStatus]:
    statuses: set[TicketStatus] = set()
    for raw in values:
        value = raw.strip()
        if value == OPEN_STATUS:
            statuses |= OPEN_STATUSES
            continue
        try:
            statuses.add(TicketStatus(value))
        except ValueError as exc:
            raise validation_error({"status": f"Unknown status: {value}"}) from exc
    return frozenset(statuses)


def parse_uuid(value: str | None, field: str) -> uuid.UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value.strip())
    except ValueError as exc:
        raise validation_error({field: "Must be a valid id"}) from exc


class TicketPresenter:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def contexts(self, actor: Actor, tickets: Sequence[Ticket]) -> dict[uuid.UUID, ActorContext]:
        collaborators = self._collaborators(tickets)
        grants = self._granted_categories(actor, tickets)
        contacts = contact_departments(self._session, actor)
        return {
            ticket.id: relationship_from(
                actor, ticket, [row.user_id for row in collaborators[ticket.id]], grants, contacts
            )
            for ticket in tickets
        }

    def context(self, actor: Actor, ticket: Ticket) -> ActorContext:
        return self.contexts(actor, [ticket])[ticket.id]

    def present(self, actor: Actor, tickets: Sequence[Ticket]) -> list[TicketOut]:
        if not tickets:
            return []
        policy = PolicyService(self._session).current()
        collaborators = self._collaborators(tickets)
        grants = self._granted_categories(actor, tickets)
        contacts = contact_departments(self._session, actor)
        user_ids: set[uuid.UUID] = set()
        for ticket in tickets:
            user_ids.update(
                user_id
                for user_id in (ticket.requester_id, ticket.owner_id, ticket.assignee_id)
                if user_id is not None
            )
            user_ids.update(row.user_id for row in collaborators[ticket.id])
        users = self._users(user_ids)
        categories = self._categories(tickets)
        attachments = self._attachments(tickets)
        timers = self._timers(tickets)
        now = self._clock.now()
        result: list[TicketOut] = []
        for ticket in tickets:
            ctx = relationship_from(
                actor, ticket, [row.user_id for row in collaborators[ticket.id]], grants, contacts
            )
            result.append(
                self._ticket_out(
                    ticket,
                    ctx,
                    policy,
                    now,
                    users,
                    categories,
                    [users[row.user_id] for row in collaborators[ticket.id]],
                    attachments[ticket.id],
                    timers[ticket.id],
                )
            )
        return result

    def present_one(self, actor: Actor, ticket: Ticket) -> TicketOut:
        return self.present(actor, [ticket])[0]

    def _ticket_out(
        self,
        ticket: Ticket,
        ctx: ActorContext,
        policy: PolicyConfig,
        now: datetime,
        users: dict[uuid.UUID, User],
        categories: dict[uuid.UUID, Category],
        collaborators: list[User],
        attachments: list[Attachment],
        timers: list[SlaTimer],
    ) -> TicketOut:
        category = categories.get(ticket.category_id) if ticket.category_id else None
        hold = (
            HoldOut(reason=ticket.hold_reason, review_date=ticket.hold_review_date)
            if ticket.status is TicketStatus.ON_HOLD
            and ticket.hold_reason is not None
            and ticket.hold_review_date is not None
            else None
        )
        feedback = (
            FeedbackOut(rating=ticket.feedback_rating, comment=ticket.feedback_comment)
            if ticket.feedback_rating is not None or ticket.feedback_comment is not None
            else None
        )
        return TicketOut(
            id=ticket.ticket_no,
            title=ticket.title,
            description=ticket.description,
            department_id=ticket.department_id,
            category_id=str(ticket.category_id) if ticket.category_id else None,
            category_name=category.name if category else None,
            priority=ticket.priority,
            requested_priority=ticket.requested_priority,
            status=ticket.status,
            confidential=ticket.confidential,
            requester=user_ref(users[ticket.requester_id]),
            owner=self._ref(users, ticket.owner_id),
            assignee=self._ref(users, ticket.assignee_id),
            collaborators=[user_ref(user) for user in collaborators],
            created_at=ticket.created_at,
            sla_started_at=ticket.sla_started_at,
            acknowledged_at=ticket.acknowledged_at,
            eta=ticket.eta,
            next_checkpoint_at=ticket.next_checkpoint_at,
            last_team_update_at=ticket.last_team_update_at,
            resolved_at=ticket.resolved_at,
            closed_at=ticket.closed_at,
            reopen_count=ticket.reopen_count,
            hold=hold,
            resolution_summary=ticket.resolution_summary,
            feedback=feedback,
            sla=build_sla_state(ticket, timers),
            allowed_actions=compute_allowed_actions(ctx, ticket, policy, now),
            attachments=[attachment_out(attachment) for attachment in attachments],
        )

    @staticmethod
    def _ref(users: dict[uuid.UUID, User], user_id: uuid.UUID | None) -> UserRef | None:
        if user_id is None:
            return None
        return user_ref(users[user_id])

    def _ids(self, tickets: Sequence[Ticket]) -> list[uuid.UUID]:
        return [ticket.id for ticket in tickets]

    def _collaborators(
        self, tickets: Sequence[Ticket]
    ) -> defaultdict[uuid.UUID, list[TicketCollaborator]]:
        grouped: defaultdict[uuid.UUID, list[TicketCollaborator]] = defaultdict(list)
        statement = (
            select(TicketCollaborator)
            .where(TicketCollaborator.ticket_id.in_(self._ids(tickets)))
            .order_by(TicketCollaborator.added_at, TicketCollaborator.user_id)
        )
        for row in self._session.scalars(statement):
            grouped[row.ticket_id].append(row)
        return grouped

    def _granted_categories(self, actor: Actor, tickets: Sequence[Ticket]) -> set[uuid.UUID]:
        category_ids = {ticket.category_id for ticket in tickets if ticket.category_id}
        if not category_ids:
            return set()
        statement = select(ConfidentialGrant.category_id).where(
            ConfidentialGrant.user_id == actor.id,
            ConfidentialGrant.revoked_at.is_(None),
            ConfidentialGrant.category_id.in_(category_ids),
        )
        return set(self._session.scalars(statement))

    def _users(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not user_ids:
            return {}
        return {
            user.id: user
            for user in self._session.scalars(select(User).where(User.id.in_(user_ids)))
        }

    def _categories(self, tickets: Sequence[Ticket]) -> dict[uuid.UUID, Category]:
        category_ids = {ticket.category_id for ticket in tickets if ticket.category_id}
        if not category_ids:
            return {}
        statement = select(Category).where(Category.id.in_(category_ids))
        return {category.id: category for category in self._session.scalars(statement)}

    def _attachments(self, tickets: Sequence[Ticket]) -> defaultdict[uuid.UUID, list[Attachment]]:
        grouped: defaultdict[uuid.UUID, list[Attachment]] = defaultdict(list)
        statement = (
            select(Attachment)
            .where(Attachment.ticket_id.in_(self._ids(tickets)))
            .order_by(Attachment.created_at, Attachment.id)
        )
        for attachment in self._session.scalars(statement):
            if attachment.ticket_id is not None:
                grouped[attachment.ticket_id].append(attachment)
        return grouped

    def _timers(self, tickets: Sequence[Ticket]) -> defaultdict[uuid.UUID, list[SlaTimer]]:
        grouped: defaultdict[uuid.UUID, list[SlaTimer]] = defaultdict(list)
        statement = select(SlaTimer).where(SlaTimer.ticket_id.in_(self._ids(tickets)))
        for timer in self._session.scalars(statement):
            grouped[timer.ticket_id].append(timer)
        return grouped


def attachment_out(attachment: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=str(attachment.id),
        name=attachment.file_name,
        size=attachment.size_bytes,
        mime=attachment.content_type,
        scan_status=attachment.scan_status,
    )


class TicketReadService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._presenter = TicketPresenter(session, clock)

    def load_visible(self, actor: Actor, ticket_no: str, *, for_update: bool = False) -> Ticket:
        statement = visible_ticket_by_number(actor, ticket_no.strip())
        if for_update:
            statement = statement.with_for_update(of=Ticket)
        ticket = self._session.scalars(statement).first()
        if ticket is None:
            raise not_found()
        return ticket

    def get_ticket(self, actor: Actor, ticket_no: str) -> TicketOut:
        return self._presenter.present_one(actor, self.load_visible(actor, ticket_no))

    def list_tickets(
        self, actor: Actor, query: TicketListQuery, params: PageParams
    ) -> Page[TicketOut]:
        sort = parse_sort(query.sort, SORTS, DEFAULT_SORT)
        filters = self.filters(actor, query)
        statement = ticket_list_statement(actor, filters, sort, self._clock.now())
        result = fetch_page(self._session, statement, params)
        return Page[TicketOut](
            items=self._presenter.present(actor, result.items),
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def filters(self, actor: Actor, query: TicketListQuery) -> TicketFilters:
        department_id = query.department_id.strip() if query.department_id else None
        scope_clause = None
        department_ids: frozenset[str] | None = (
            frozenset({department_id}) if department_id else None
        )
        if query.scope is TicketScope.MINE:
            scope_clause = mine_clause(actor)
        elif query.scope is TicketScope.ASSIGNED:
            scope_clause = assigned_clause(actor)
        elif query.scope is TicketScope.QUEUE:
            if not actor.is_spoke:
                raise forbidden()
            if department_id and department_id not in actor.spoke_department_ids:
                raise forbidden()
            scope_clause = in_departments(
                {department_id} if department_id else actor.spoke_department_ids
            )
            department_ids = None
        else:
            policy = PolicyService(self._session).current()
            if not has_permission(actor, TICKETS_VIEW_ALL, policy.admins_can_manage_departments):
                raise forbidden()
        if query.escalation_level is not None and not 0 <= query.escalation_level <= 3:
            raise validation_error({"escalation_level": "Must be between 0 and 3"})
        return TicketFilters(
            statuses=parse_statuses(query.statuses),
            priorities=frozenset(query.priorities),
            department_ids=department_ids,
            category_id=parse_uuid(query.category_id, "category_id"),
            requester_id=parse_uuid(query.requester_id, "requester_id"),
            assignee_id=parse_uuid(query.assignee_id, "assignee_id"),
            sla_state=query.sla_state,
            escalation_level=query.escalation_level,
            confidential=query.confidential,
            overdue_eta=query.overdue_eta,
            unassigned=query.unassigned,
            awaiting_before=query.awaiting_before,
            created_from=query.created_from,
            created_to=query.created_to,
            q=query.q,
            extra=(scope_clause,) if scope_clause is not None else (),
        )

    def timeline(self, actor: Actor, ticket_no: str) -> list[TimelineEventOut]:
        ticket = self.load_visible(actor, ticket_no)
        ctx = self._presenter.context(actor, ticket)
        staff = bool(actor_classes(ctx, ticket.confidential) & STAFF_CLASSES)
        statement = (
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket.id)
            .order_by(TicketEvent.at, TicketEvent.id)
        )
        if not staff:
            statement = statement.where(TicketEvent.is_public.is_(True))
        events = list(self._session.scalars(statement))
        actor_ids = {event.actor_id for event in events if event.actor_id is not None}
        users = (
            {
                user.id: user
                for user in self._session.scalars(select(User).where(User.id.in_(actor_ids)))
            }
            if actor_ids
            else {}
        )
        return [self._event_out(event, users, staff) for event in events]

    @staticmethod
    def _event_out(
        event: TicketEvent, users: dict[uuid.UUID, User], staff: bool
    ) -> TimelineEventOut:
        author: UserRef | SystemActor = (
            user_ref(users[event.actor_id])
            if event.actor_id is not None and event.actor_id in users
            else SYSTEM_ACTOR
        )
        detail = event.detail
        if not staff and event.public_detail is not None:
            detail = event.public_detail
        return TimelineEventOut(
            id=str(event.id),
            at=event.at,
            actor=author,
            type=event.kind,
            action=event.action,
            detail=detail,
            body=event.body,
            public=event.is_public,
        )
