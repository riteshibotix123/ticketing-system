import uuid
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Final

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.enums import ProtectedActionKind, Role
from app.core.events import (
    CollaboratorChanged,
    CommentAdded,
    ConfidentialGrantChanged,
    EscalationRaised,
    EventBus,
    ProtectedActionDecided,
    ProtectedActionRequested,
    SignupVerified,
    SlaWarningRaised,
    TicketAcknowledged,
    TicketAssigned,
    TicketCancelled,
    TicketClosed,
    TicketCreated,
    TicketDomainEvent,
    TicketEtaChanged,
    TicketPriorityChanged,
    TicketReopened,
    TicketResolved,
    TicketStatusChanged,
    TicketTransferred,
    UserDeactivated,
)
from app.models.identity import ProtectedActionRequest, SignupRequest, User
from app.models.org import Category, ConfidentialGrant
from app.models.sla import SlaTimer, TimerKind
from app.models.ticket import Ticket, TicketEvent
from app.policy.actors import load_actor
from app.policy.allowed_actions import ActorClass, actor_classes
from app.policy.relationships import load_relationship
from app.services.handlers.recipients import (
    Recipient,
    Recipients,
    active_user,
    active_users_with_roles,
    collaborators,
    department_spokes,
    owner_and_assignee,
    requester,
    visible_only,
)
from app.services.notifications import Message, Notifier, ticket_message
from app.services.sla.escalation import CREATION_CONTACT, resolve_recipients
from app.services.workflow.common import format_time, status_label

TEAM_CLASSES: Final = frozenset({ActorClass.TEAM, ActorClass.ASSIGNEE})
ACTION_VERBS: Final = {
    ProtectedActionKind.DEACTIVATE_SUPER_ADMIN: "deactivate",
    ProtectedActionKind.DEMOTE_SUPER_ADMIN: "demote",
}
MANAGERS: Final = (Role.ADMIN, Role.SUPER_ADMIN)

type Plan = tuple[Recipients, Message]
type TicketPlanner[E: TicketDomainEvent] = Callable[[Session, Ticket, E], Plan | None]


def deliver(session: Session, at: datetime, entries: Iterable[Recipient], message: Message) -> None:
    notifier = Notifier(session, at)
    for entry in entries:
        notifier.send(entry.user, message, email=entry.email)


def _for_ticket[E: TicketDomainEvent](planner: TicketPlanner[E]) -> Callable[[Session, E], None]:
    def handler(session: Session, event: E) -> None:
        ticket = session.get(Ticket, event.ticket_id)
        if ticket is None:
            return
        plan = planner(session, ticket, event)
        if plan is None:
            return
        recipients, message = plan
        deliver(
            session, event.occurred_at, visible_only(session, ticket, recipients.items()), message
        )

    return handler


def _name(session: Session, user_id: uuid.UUID | None) -> str:
    user = session.get(User, user_id) if user_id is not None else None
    return user.name if user is not None else "System"


def _timer_label(kind: TimerKind) -> str:
    return kind.value.replace("_", " ")


def _cycle(session: Session, ticket: Ticket, kind: TimerKind) -> int:
    statement = select(SlaTimer.cycle).where(SlaTimer.ticket_id == ticket.id, SlaTimer.kind == kind)
    return session.scalar(statement) or 1


def plan_created(session: Session, ticket: Ticket, event: TicketCreated) -> Plan:
    recipients = (
        Recipients(event.actor_id)
        .add(requester(session, ticket), email=True)
        .add(department_spokes(session, ticket.department_id), email=True)
    )
    text = f"New ticket {ticket.ticket_no} in {ticket.department_id}: {ticket.title}"
    return recipients, ticket_message(ticket, kind="ticket_created", text=text)


def plan_acknowledged(session: Session, ticket: Ticket, event: TicketAcknowledged) -> Plan:
    owner = _name(session, ticket.owner_id)
    eta = format_time(ticket.eta) if ticket.eta is not None else None
    next_update = (
        format_time(ticket.next_checkpoint_at) if ticket.next_checkpoint_at is not None else None
    )
    text = f"Your ticket {ticket.ticket_no} was acknowledged by {owner}."
    if eta is not None:
        text = f"{text} ETA {eta}"
    elif next_update is not None:
        text = f"{text} Next update by {next_update}"
    recipients = Recipients(event.actor_id).add(requester(session, ticket), email=True)
    message = ticket_message(
        ticket,
        kind="ticket_acknowledged",
        text=text,
        extras={"owner": owner, "eta": eta, "next_update": next_update},
    )
    return recipients, message


def plan_assigned(session: Session, ticket: Ticket, event: TicketAssigned) -> Plan:
    recipients = (
        Recipients(event.actor_id)
        .add([active_user(session, ticket.assignee_id)], email=True)
        .add(requester(session, ticket), email=False)
        .add(department_spokes(session, ticket.department_id), email=False)
    )
    assignee = _name(session, ticket.assignee_id)
    text = f"Ticket {ticket.ticket_no} was assigned to {assignee}: {ticket.title}"
    return recipients, ticket_message(ticket, kind="ticket_assigned", text=text)


def plan_status_changed(session: Session, ticket: Ticket, event: TicketStatusChanged) -> Plan:
    recipients = (
        Recipients(event.actor_id)
        .add(requester(session, ticket), email=True)
        .add(owner_and_assignee(session, ticket), email=False)
    )
    text = f"Ticket {ticket.ticket_no} is now {status_label(event.to_status)}"
    return recipients, ticket_message(ticket, kind="status_changed", text=text)


def _comment_by_team(session: Session, ticket: Ticket, comment: TicketEvent) -> bool:
    if comment.actor_id is None:
        return False
    author = load_actor(session, comment.actor_id)
    if author is None:
        return False
    ctx = load_relationship(session, author, ticket)
    if ctx.is_requester:
        return False
    return bool(actor_classes(ctx, ticket.confidential) & TEAM_CLASSES)


def plan_comment(session: Session, ticket: Ticket, event: CommentAdded) -> Plan | None:
    comment = session.get(TicketEvent, event.ticket_event_id)
    if comment is None:
        return None
    author = _name(session, comment.actor_id)
    staff = [
        *owner_and_assignee(session, ticket),
        *department_spokes(session, ticket.department_id),
    ]
    recipients = Recipients(event.actor_id)
    if event.internal:
        recipients.add(staff, email=False)
        text = f"New internal note on {ticket.ticket_no} from {author}"
        return recipients, ticket_message(ticket, kind="internal_note", text=text, email=False)
    if _comment_by_team(session, ticket, comment):
        recipients.add(requester(session, ticket), email=True)
        recipients.add(collaborators(session, ticket), email=True)
    else:
        recipients.add(staff, email=True)
    text = f"New comment on {ticket.ticket_no} from {author}"
    message = ticket_message(
        ticket,
        kind="comment_added",
        text=text,
        extras={"author": author, "body": comment.body or ""},
    )
    return recipients, message


def plan_eta_changed(session: Session, ticket: Ticket, event: TicketEtaChanged) -> Plan:
    new_eta = format_time(event.new)
    old_eta = format_time(event.old) if event.old is not None else None
    if old_eta is None:
        text = f"ETA for {ticket.ticket_no} set to {new_eta}"
    elif event.is_extension:
        text = f"ETA for {ticket.ticket_no} extended from {old_eta} to {new_eta}"
    else:
        text = f"ETA for {ticket.ticket_no} changed from {old_eta} to {new_eta}"
    recipients = Recipients(event.actor_id).add(requester(session, ticket), email=True)
    message = ticket_message(
        ticket,
        kind="eta_changed",
        text=text,
        extras={"old_eta": old_eta, "new_eta": new_eta, "is_extension": event.is_extension},
    )
    return recipients, message


def plan_priority_changed(session: Session, ticket: Ticket, event: TicketPriorityChanged) -> Plan:
    recipients = Recipients(event.actor_id).add(owner_and_assignee(session, ticket), email=False)
    text = f"Priority of {ticket.ticket_no} changed from {event.old.value} to {event.new.value}"
    return recipients, ticket_message(ticket, kind="priority_changed", text=text, email=False)


def plan_transferred(session: Session, ticket: Ticket, event: TicketTransferred) -> Plan:
    recipients = (
        Recipients(event.actor_id)
        .add(requester(session, ticket), email=True)
        .add(department_spokes(session, event.from_department), email=True)
        .add(department_spokes(session, event.to_department), email=True)
    )
    text = (
        f"Ticket {ticket.ticket_no} was transferred from {event.from_department} "
        f"to {event.to_department}"
    )
    return recipients, ticket_message(ticket, kind="transferred", text=text)


def plan_resolved(session: Session, ticket: Ticket, event: TicketResolved) -> Plan:
    recipients = Recipients(event.actor_id).add(requester(session, ticket), email=True)
    text = f"Ticket {ticket.ticket_no} was resolved. Please confirm or reopen it"
    message = ticket_message(
        ticket,
        kind="resolved",
        text=text,
        extras={"summary": ticket.resolution_summary or ""},
    )
    return recipients, message


def plan_closed(session: Session, ticket: Ticket, event: TicketClosed) -> Plan:
    recipients = (
        Recipients(event.actor_id)
        .add(requester(session, ticket), email=True)
        .add(owner_and_assignee(session, ticket), email=False)
    )
    text = f"Ticket {ticket.ticket_no} was closed"
    return recipients, ticket_message(ticket, kind="closed", text=text)


def plan_reopened(session: Session, ticket: Ticket, event: TicketReopened) -> Plan:
    recipients = (
        Recipients(event.actor_id)
        .add(owner_and_assignee(session, ticket), email=True)
        .add(department_spokes(session, ticket.department_id), email=True)
        .add(requester(session, ticket), email=False)
    )
    text = f"Ticket {ticket.ticket_no} was reopened"
    return recipients, ticket_message(ticket, kind="reopened", text=text)


def plan_cancelled(session: Session, ticket: Ticket, event: TicketCancelled) -> Plan:
    recipients = (
        Recipients(event.actor_id)
        .add(requester(session, ticket), email=True)
        .add(owner_and_assignee(session, ticket), email=False)
    )
    text = f"Ticket {ticket.ticket_no} was cancelled"
    return recipients, ticket_message(ticket, kind="cancelled", text=text)


def plan_collaborator(session: Session, ticket: Ticket, event: CollaboratorChanged) -> Plan | None:
    if not event.added:
        return None
    recipients = Recipients(event.actor_id).add([active_user(session, event.user_id)], email=True)
    text = f"You were added as a collaborator on {ticket.ticket_no}: {ticket.title}"
    return recipients, ticket_message(ticket, kind="collaborator_added", text=text)


def plan_sla_warning(session: Session, ticket: Ticket, event: SlaWarningRaised) -> Plan:
    cycle = _cycle(session, ticket, event.timer_kind)
    recipients = Recipients(event.actor_id).add(
        resolve_recipients(session, ticket, event.level), email=True
    )
    text = f"L{event.level} {_timer_label(event.timer_kind)} warning on {ticket.ticket_no}"
    dedupe_key = f"sla_warning:{ticket.id}:{event.timer_kind.value}:{cycle}:L{event.level}"
    message = ticket_message(
        ticket,
        kind="sla_warning",
        text=text,
        extras={"timer": _timer_label(event.timer_kind), "level": event.level},
        dedupe_key=dedupe_key,
    )
    return recipients, message


def plan_escalation(session: Session, ticket: Ticket, event: EscalationRaised) -> Plan | None:
    creation_contact = event.step_key == CREATION_CONTACT
    if event.level < 2 and not creation_contact:
        return None
    cycle = _cycle(session, ticket, event.timer_kind)
    users = resolve_recipients(session, ticket, event.level, creation_contact=creation_contact)
    recipients = Recipients(event.actor_id).add(users, email=True)
    text = (
        f"Critical ticket {ticket.ticket_no} raised in {ticket.department_id}: {ticket.title}"
        if creation_contact
        else f"L{event.level} {_timer_label(event.timer_kind)} breach on {ticket.ticket_no}"
    )
    dedupe_key = f"escalation:{ticket.id}:{event.timer_kind.value}:{cycle}:{event.step_key}"
    message = ticket_message(
        ticket,
        kind="escalation",
        text=text,
        extras={"timer": _timer_label(event.timer_kind), "level": event.level},
        critical=True,
        dedupe_key=dedupe_key,
    )
    return recipients, message


def on_signup_verified(session: Session, event: SignupVerified) -> None:
    request = session.get(SignupRequest, event.signup_request_id)
    if request is None:
        return
    applicant = session.get(User, request.user_id)
    if applicant is None:
        return
    roles = MANAGERS if request.requested_role is Role.EMPLOYEE else (Role.SUPER_ADMIN,)
    recipients = Recipients(event.actor_id, applicant.id).add(
        active_users_with_roles(session, *roles), email=True
    )
    role = request.requested_role.value.replace("_", " ")
    message = Message(
        kind="signup_pending",
        text=f"Signup request from {applicant.name} ({role}) awaits approval",
        template="signup_pending",
        context={
            "applicant": applicant.name,
            "applicant_email": applicant.email,
            "requested_role": role,
            "department": request.requested_department_id,
        },
    )
    deliver(session, event.occurred_at, recipients.items(), message)


def on_user_deactivated(session: Session, event: UserDeactivated) -> None:
    if event.open_ticket_count <= 0:
        return
    name = _name(session, event.user_id)
    recipients = Recipients(event.actor_id, event.user_id).add(
        active_users_with_roles(session, *MANAGERS), email=True
    )
    message = Message(
        kind="user_deactivated_open_tickets",
        text=f"{name} was deactivated with {event.open_ticket_count} open tickets",
        template="user_deactivated_open_tickets",
        context={"user_name": name, "open_ticket_count": event.open_ticket_count},
        critical=True,
    )
    deliver(session, event.occurred_at, recipients.items(), message)


def on_protected_action_requested(session: Session, event: ProtectedActionRequested) -> None:
    request = session.get(ProtectedActionRequest, event.protected_action_id)
    if request is None:
        return
    requester_name = _name(session, request.requested_by_id)
    target = _name(session, request.target_user_id)
    verb = ACTION_VERBS[request.kind]
    recipients = Recipients(event.actor_id, request.requested_by_id, request.target_user_id).add(
        active_users_with_roles(session, Role.SUPER_ADMIN), email=True
    )
    message = Message(
        kind="protected_action_requested",
        text=f"{requester_name} requested to {verb} Super Admin {target}",
        template="protected_action_requested",
        context={"requester": requester_name, "target": target, "action": verb},
        critical=True,
    )
    deliver(session, event.occurred_at, recipients.items(), message)


def on_protected_action_decided(session: Session, event: ProtectedActionDecided) -> None:
    request = session.get(ProtectedActionRequest, event.protected_action_id)
    if request is None:
        return
    target = _name(session, request.target_user_id)
    verb = ACTION_VERBS[request.kind]
    recipients = (
        Recipients(event.actor_id)
        .add([active_user(session, request.requested_by_id)], email=True)
        .add(active_users_with_roles(session, Role.SUPER_ADMIN), email=True)
    )
    message = Message(
        kind="protected_action_decided",
        text=f"The request to {verb} Super Admin {target} was {request.status.value}",
        template="protected_action_decided",
        context={"target": target, "action": verb, "status": request.status.value},
        critical=True,
    )
    deliver(session, event.occurred_at, recipients.items(), message)


def on_grant_changed(session: Session, event: ConfidentialGrantChanged) -> None:
    category = session.get(Category, event.category_id)
    if category is None:
        return
    granted = bool(
        session.scalar(
            select(
                exists().where(
                    ConfidentialGrant.user_id == event.user_id,
                    ConfidentialGrant.category_id == event.category_id,
                    ConfidentialGrant.revoked_at.is_(None),
                )
            )
        )
    )
    text = (
        f"You were granted access to confidential category {category.name}"
        if granted
        else f"Your access to confidential category {category.name} was revoked"
    )
    recipients = Recipients(event.actor_id).add([active_user(session, event.user_id)], email=True)
    message = Message(
        kind="confidential_grant_changed",
        text=text,
        template="confidential_grant_changed",
        context={"category": category.name, "granted": granted},
    )
    deliver(session, event.occurred_at, recipients.items(), message)


def register_notification_handlers(target: EventBus) -> None:
    target.register(SignupVerified, on_signup_verified)
    target.register(UserDeactivated, on_user_deactivated)
    target.register(ProtectedActionRequested, on_protected_action_requested)
    target.register(ProtectedActionDecided, on_protected_action_decided)
    target.register(ConfidentialGrantChanged, on_grant_changed)
    target.register(TicketCreated, _for_ticket(plan_created))
    target.register(TicketAcknowledged, _for_ticket(plan_acknowledged))
    target.register(TicketAssigned, _for_ticket(plan_assigned))
    target.register(TicketStatusChanged, _for_ticket(plan_status_changed))
    target.register(CommentAdded, _for_ticket(plan_comment))
    target.register(TicketEtaChanged, _for_ticket(plan_eta_changed))
    target.register(TicketPriorityChanged, _for_ticket(plan_priority_changed))
    target.register(TicketTransferred, _for_ticket(plan_transferred))
    target.register(TicketResolved, _for_ticket(plan_resolved))
    target.register(TicketClosed, _for_ticket(plan_closed))
    target.register(TicketReopened, _for_ticket(plan_reopened))
    target.register(TicketCancelled, _for_ticket(plan_cancelled))
    target.register(CollaboratorChanged, _for_ticket(plan_collaborator))
    target.register(SlaWarningRaised, _for_ticket(plan_sla_warning))
    target.register(EscalationRaised, _for_ticket(plan_escalation))
