from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal

from app.core.enums import TicketAction, TicketStatus
from app.core.errors import ErrorCode
from app.models.ticket import Ticket
from app.policy.relationships import ActorContext
from app.policy.visibility import is_visible
from app.services.policy import PolicyConfig


class ActorClass(StrEnum):
    REQUESTER = "requester"
    COLLABORATOR = "collaborator"
    ASSIGNEE = "assignee"
    TEAM = "team"


Rule = tuple[frozenset[ActorClass], frozenset[TicketStatus]]

ACTIVE_STATUSES: Final = frozenset(
    {
        TicketStatus.NEW,
        TicketStatus.ACKNOWLEDGED,
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.AWAITING_REQUESTER,
        TicketStatus.ON_HOLD,
        TicketStatus.REOPENED,
    }
)
WORKING_STATUSES: Final = ACTIVE_STATUSES - {TicketStatus.NEW}
DISCUSSION_STATUSES: Final = frozenset(TicketStatus) - {TicketStatus.CLOSED, TicketStatus.CANCELLED}
REOPENABLE_STATUSES: Final = frozenset({TicketStatus.RESOLVED, TicketStatus.CLOSED})

TEAM: Final = frozenset({ActorClass.TEAM})
WORKERS: Final = frozenset({ActorClass.TEAM, ActorClass.ASSIGNEE})
REQUESTER: Final = frozenset({ActorClass.REQUESTER})
PARTICIPANTS: Final = frozenset(ActorClass)

ACTION_RULES: Final[Mapping[TicketAction, tuple[Rule, ...]]] = MappingProxyType(
    {
        TicketAction.ACKNOWLEDGE: ((TEAM, frozenset({TicketStatus.NEW})),),
        TicketAction.ASSIGN: ((TEAM, WORKING_STATUSES),),
        TicketAction.TRANSFER: ((TEAM, ACTIVE_STATUSES),),
        TicketAction.CHANGE_PRIORITY: ((TEAM, ACTIVE_STATUSES),),
        TicketAction.REVISE_ETA: ((WORKERS, WORKING_STATUSES),),
        TicketAction.START_WORK: (
            (
                WORKERS,
                frozenset(
                    {TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED, TicketStatus.REOPENED}
                ),
            ),
        ),
        TicketAction.ASK_REQUESTER: ((WORKERS, frozenset({TicketStatus.IN_PROGRESS})),),
        TicketAction.HOLD: ((WORKERS, frozenset({TicketStatus.IN_PROGRESS})),),
        TicketAction.RESUME: (
            (WORKERS, frozenset({TicketStatus.AWAITING_REQUESTER, TicketStatus.ON_HOLD})),
        ),
        TicketAction.RESOLVE: ((WORKERS, frozenset({TicketStatus.IN_PROGRESS})),),
        TicketAction.CONFIRM_CLOSURE: ((REQUESTER, frozenset({TicketStatus.RESOLVED})),),
        TicketAction.REOPEN: ((REQUESTER | TEAM, REOPENABLE_STATUSES),),
        TicketAction.CANCEL: (
            (TEAM, ACTIVE_STATUSES),
            (REQUESTER, frozenset({TicketStatus.NEW})),
        ),
        TicketAction.CLOSE_ADMIN: ((TEAM, frozenset({TicketStatus.RESOLVED})),),
        TicketAction.COMMENT: ((PARTICIPANTS, DISCUSSION_STATUSES),),
        TicketAction.INTERNAL_NOTE: ((WORKERS, DISCUSSION_STATUSES),),
        TicketAction.MANAGE_COLLABORATORS: ((TEAM, DISCUSSION_STATUSES),),
    }
)
NOT_FOR_REQUESTER_AS_TEAM: Final = frozenset({TicketAction.ACKNOWLEDGE, TicketAction.RESOLVE})
NEVER_FOR_REQUESTER: Final = frozenset({TicketAction.RESOLVE})

Denial = Literal[ErrorCode.FORBIDDEN, ErrorCode.INVALID_TRANSITION]


def actor_classes(ctx: ActorContext, confidential: bool) -> frozenset[ActorClass]:
    if not is_visible(ctx, confidential):
        return frozenset()
    flags = {
        ActorClass.REQUESTER: ctx.is_requester,
        ActorClass.COLLABORATOR: ctx.is_collaborator,
        ActorClass.ASSIGNEE: ctx.is_assignee,
        ActorClass.TEAM: ctx.is_department_spoke
        or ctx.is_owner
        or ctx.is_admin
        or ctx.is_super_admin,
    }
    return frozenset(actor_class for actor_class, held in flags.items() if held)


def classes_for_action(
    action: TicketAction, ctx: ActorContext, confidential: bool
) -> frozenset[ActorClass]:
    classes = actor_classes(ctx, confidential)
    if not ctx.is_requester:
        return classes
    if action in NEVER_FOR_REQUESTER:
        return frozenset()
    if action in NOT_FOR_REQUESTER_AS_TEAM:
        return classes - TEAM
    return classes


def reopen_available(ticket: Ticket, policy: PolicyConfig, now: datetime) -> bool:
    if ticket.resolved_at is None or ticket.reopen_count >= policy.max_reopens:
        return False
    return now <= ticket.resolved_at + timedelta(days=policy.reopen_window_days)


def is_action_allowed(
    action: TicketAction,
    ctx: ActorContext,
    ticket: Ticket,
    policy: PolicyConfig,
    now: datetime,
) -> bool:
    classes = classes_for_action(action, ctx, ticket.confidential)
    permitted = any(
        rule_classes & classes and ticket.status in statuses
        for rule_classes, statuses in ACTION_RULES[action]
    )
    if permitted and action is TicketAction.REOPEN:
        return reopen_available(ticket, policy, now)
    return permitted


def compute_allowed_actions(
    actor_ctx: ActorContext, ticket: Ticket, policy: PolicyConfig, now: datetime
) -> list[TicketAction]:
    return [
        action
        for action in TicketAction
        if is_action_allowed(action, actor_ctx, ticket, policy, now)
    ]


def classify_denial(action: TicketAction, actor_ctx: ActorContext, ticket: Ticket) -> Denial:
    classes = classes_for_action(action, actor_ctx, ticket.confidential)
    if any(rule_classes & classes for rule_classes, _ in ACTION_RULES[action]):
        return ErrorCode.INVALID_TRANSITION
    return ErrorCode.FORBIDDEN
