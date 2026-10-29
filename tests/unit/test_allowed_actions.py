import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import Priority, Role, TicketAction, TicketStatus
from app.core.errors import ErrorCode
from app.models import Ticket
from app.policy import Actor
from app.policy.allowed_actions import classify_denial, compute_allowed_actions
from app.policy.relationships import ActorContext, relationship_from
from app.services.policy import PolicyConfig

A = TicketAction
S = TicketStatus
NOW = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)
CATEGORY_ID = uuid.uuid4()
POLICY = PolicyConfig(
    initial_response_hours=24,
    warning_hours={Priority.LOW: 18, Priority.MEDIUM: 18, Priority.HIGH: 18, Priority.CRITICAL: 12},
    l3_hours={Priority.LOW: 48, Priority.MEDIUM: 48, Priority.HIGH: 36, Priority.CRITICAL: 30},
    update_warning_hours=20,
    update_cadence_hours=24,
    eta_warning_hours=2,
    escalation_repeat_hours=24,
    requester_reminder_hours=48,
    auto_close_business_days=3,
    reopen_window_days=7,
    max_reopens=3,
    sla_mode="calendar",
    admins_can_manage_departments=True,
)


def make_actor(
    role: Role = Role.EMPLOYEE, spoke_departments: frozenset[str] = frozenset()
) -> Actor:
    return Actor(
        id=uuid.uuid4(),
        global_role=role,
        department_id="HR",
        spoke_department_ids=spoke_departments,
        name="Actor",
        email=f"{uuid.uuid4().hex}@ibotix.ai",
    )


REQUESTER = make_actor()
REQUESTER_SPOKE = make_actor(spoke_departments=frozenset({"IT"}))
ASSIGNEE = make_actor()
COLLABORATOR = make_actor()
OWNER = make_actor()
SPOKE = make_actor(spoke_departments=frozenset({"IT"}))
OTHER_SPOKE = make_actor(spoke_departments=frozenset({"HR"}))
ADMIN = make_actor(Role.ADMIN)
SUPER_ADMIN = make_actor(Role.SUPER_ADMIN)
UNRELATED = make_actor()


def make_ticket(
    status: TicketStatus,
    *,
    requester: Actor = REQUESTER,
    assignee: Actor | None = ASSIGNEE,
    owner: Actor | None = OWNER,
    confidential: bool = False,
    resolved_at: datetime | None = NOW - timedelta(days=1),
    reopen_count: int = 0,
) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        ticket_no="IBX-IT-2026-000001",
        origin_department_code="IT",
        department_id="IT",
        category_id=CATEGORY_ID,
        status=status,
        confidential=confidential,
        requester_id=requester.id,
        assignee_id=assignee.id if assignee else None,
        owner_id=owner.id if owner else None,
        resolved_at=resolved_at,
        reopen_count=reopen_count,
    )


def context(actor: Actor, ticket: Ticket, *, granted: bool = False) -> ActorContext:
    grants = {CATEGORY_ID} if granted else set()
    return relationship_from(actor, ticket, {COLLABORATOR.id}, grants, set())


DISCUSSION = {A.COMMENT, A.INTERNAL_NOTE, A.MANAGE_COLLABORATORS}
TEAM_WORKING = {A.ASSIGN, A.CHANGE_PRIORITY, A.REVISE_ETA, A.CANCEL, A.TRANSFER, *DISCUSSION}
TEAM_EXPECTED: dict[TicketStatus, set[TicketAction]] = {
    S.NEW: {A.ACKNOWLEDGE, A.CHANGE_PRIORITY, A.CANCEL, A.TRANSFER, *DISCUSSION},
    S.ACKNOWLEDGED: {*TEAM_WORKING, A.START_WORK},
    S.ASSIGNED: {*TEAM_WORKING, A.START_WORK},
    S.IN_PROGRESS: {*TEAM_WORKING, A.ASK_REQUESTER, A.HOLD, A.RESOLVE},
    S.AWAITING_REQUESTER: {*TEAM_WORKING, A.RESUME},
    S.ON_HOLD: {*TEAM_WORKING, A.RESUME},
    S.RESOLVED: {A.REOPEN, A.CLOSE_ADMIN, *DISCUSSION},
    S.CLOSED: {A.REOPEN},
    S.REOPENED: {*TEAM_WORKING, A.START_WORK},
    S.CANCELLED: set(),
}
NOTES = {A.COMMENT, A.INTERNAL_NOTE}
ASSIGNEE_EXPECTED: dict[TicketStatus, set[TicketAction]] = {
    S.NEW: NOTES,
    S.ACKNOWLEDGED: {A.REVISE_ETA, A.START_WORK, *NOTES},
    S.ASSIGNED: {A.REVISE_ETA, A.START_WORK, *NOTES},
    S.IN_PROGRESS: {A.REVISE_ETA, A.ASK_REQUESTER, A.HOLD, A.RESOLVE, *NOTES},
    S.AWAITING_REQUESTER: {A.REVISE_ETA, A.RESUME, *NOTES},
    S.ON_HOLD: {A.REVISE_ETA, A.RESUME, *NOTES},
    S.RESOLVED: NOTES,
    S.CLOSED: set(),
    S.REOPENED: {A.REVISE_ETA, A.START_WORK, *NOTES},
    S.CANCELLED: set(),
}
REQUESTER_EXPECTED: dict[TicketStatus, set[TicketAction]] = {
    S.NEW: {A.CANCEL, A.COMMENT},
    S.ACKNOWLEDGED: {A.COMMENT},
    S.ASSIGNED: {A.COMMENT},
    S.IN_PROGRESS: {A.COMMENT},
    S.AWAITING_REQUESTER: {A.COMMENT},
    S.ON_HOLD: {A.COMMENT},
    S.RESOLVED: {A.CONFIRM_CLOSURE, A.REOPEN, A.COMMENT},
    S.CLOSED: {A.REOPEN},
    S.REOPENED: {A.COMMENT},
    S.CANCELLED: set(),
}
COLLABORATOR_EXPECTED: dict[TicketStatus, set[TicketAction]] = {
    status: set() if status in {S.CLOSED, S.CANCELLED} else {A.COMMENT} for status in S
}
REQUESTER_TEAM_EXPECTED: dict[TicketStatus, set[TicketAction]] = {
    status: (TEAM_EXPECTED[status] | REQUESTER_EXPECTED[status]) - {A.ACKNOWLEDGE, A.RESOLVE}
    for status in S
}
NOBODY: dict[TicketStatus, set[TicketAction]] = {status: set() for status in S}

MATRIX: list[tuple[str, Actor, bool, dict[TicketStatus, set[TicketAction]]]] = [
    ("requester", REQUESTER, False, REQUESTER_EXPECTED),
    ("requester_spoke", REQUESTER_SPOKE, False, REQUESTER_TEAM_EXPECTED),
    ("assignee", ASSIGNEE, False, ASSIGNEE_EXPECTED),
    ("collaborator", COLLABORATOR, False, COLLABORATOR_EXPECTED),
    ("owner_without_visibility", OWNER, False, NOBODY),
    ("spoke", SPOKE, False, TEAM_EXPECTED),
    ("spoke_with_grant", SPOKE, True, TEAM_EXPECTED),
    ("other_spoke", OTHER_SPOKE, False, NOBODY),
    ("admin", ADMIN, False, TEAM_EXPECTED),
    ("admin_with_grant", ADMIN, True, TEAM_EXPECTED),
    ("super_admin", SUPER_ADMIN, False, TEAM_EXPECTED),
    ("unrelated", UNRELATED, False, NOBODY),
    ("unrelated_with_grant", UNRELATED, True, NOBODY),
]


@pytest.mark.parametrize("status", list(S))
@pytest.mark.parametrize(
    ("actor", "granted", "expected"),
    [(actor, granted, expected) for _, actor, granted, expected in MATRIX],
    ids=[name for name, *_ in MATRIX],
)
def test_allowed_actions_non_confidential(
    status: TicketStatus,
    actor: Actor,
    granted: bool,
    expected: dict[TicketStatus, set[TicketAction]],
) -> None:
    requester = REQUESTER_SPOKE if actor is REQUESTER_SPOKE else REQUESTER
    ticket = make_ticket(status, requester=requester)
    actions = compute_allowed_actions(context(actor, ticket, granted=granted), ticket, POLICY, NOW)
    assert set(actions) == expected[status]
    assert actions == [action for action in TicketAction if action in expected[status]]


CONFIDENTIAL_MATRIX: list[tuple[str, Actor, bool, dict[TicketStatus, set[TicketAction]]]] = [
    ("requester", REQUESTER, False, REQUESTER_EXPECTED),
    ("assignee", ASSIGNEE, False, ASSIGNEE_EXPECTED),
    ("collaborator", COLLABORATOR, False, COLLABORATOR_EXPECTED),
    ("spoke_without_grant", SPOKE, False, NOBODY),
    ("spoke_with_grant", SPOKE, True, TEAM_EXPECTED),
    ("other_spoke_with_grant", OTHER_SPOKE, True, NOBODY),
    ("admin_without_grant", ADMIN, False, NOBODY),
    ("admin_with_grant", ADMIN, True, TEAM_EXPECTED),
    ("super_admin", SUPER_ADMIN, False, TEAM_EXPECTED),
    ("unrelated", UNRELATED, False, NOBODY),
    ("unrelated_with_grant", UNRELATED, True, NOBODY),
]


@pytest.mark.parametrize("status", list(S))
@pytest.mark.parametrize(
    ("actor", "granted", "expected"),
    [(actor, granted, expected) for _, actor, granted, expected in CONFIDENTIAL_MATRIX],
    ids=[name for name, *_ in CONFIDENTIAL_MATRIX],
)
def test_allowed_actions_confidential(
    status: TicketStatus,
    actor: Actor,
    granted: bool,
    expected: dict[TicketStatus, set[TicketAction]],
) -> None:
    ticket = make_ticket(status, confidential=True)
    actions = compute_allowed_actions(context(actor, ticket, granted=granted), ticket, POLICY, NOW)
    assert set(actions) == expected[status]


@pytest.mark.parametrize("status", list(S))
def test_owner_who_is_still_visible_acts_as_team(status: TicketStatus) -> None:
    ticket = make_ticket(status, owner=COLLABORATOR)
    actions = compute_allowed_actions(context(COLLABORATOR, ticket), ticket, POLICY, NOW)
    assert set(actions) == TEAM_EXPECTED[status]


@pytest.mark.parametrize("status", list(S))
def test_requester_assignee_never_resolves(status: TicketStatus) -> None:
    ticket = make_ticket(status, assignee=REQUESTER)
    actions = compute_allowed_actions(context(REQUESTER, ticket), ticket, POLICY, NOW)
    expected = (ASSIGNEE_EXPECTED[status] | REQUESTER_EXPECTED[status]) - {A.RESOLVE}
    assert set(actions) == expected


@pytest.mark.parametrize("status", [S.RESOLVED, S.CLOSED])
@pytest.mark.parametrize("actor", [REQUESTER, SPOKE], ids=["requester", "team"])
@pytest.mark.parametrize(
    ("resolved_at", "reopen_count", "expected"),
    [
        (NOW - timedelta(days=7), 0, True),
        (NOW - timedelta(days=7, seconds=1), 0, False),
        (NOW - timedelta(days=6, hours=23), 2, True),
        (NOW - timedelta(days=1), 3, False),
        (NOW, 0, True),
        (None, 0, False),
    ],
    ids=["window_edge", "window_passed", "last_reopen", "max_reopens", "just_resolved", "never"],
)
def test_reopen_window_and_count(
    status: TicketStatus,
    actor: Actor,
    resolved_at: datetime | None,
    reopen_count: int,
    expected: bool,
) -> None:
    ticket = make_ticket(status, resolved_at=resolved_at, reopen_count=reopen_count)
    actions = compute_allowed_actions(context(actor, ticket), ticket, POLICY, NOW)
    assert (A.REOPEN in actions) is expected


def test_reopen_uses_policy_values() -> None:
    policy = POLICY.model_copy(update={"reopen_window_days": 1, "max_reopens": 1})
    ticket = make_ticket(S.RESOLVED, resolved_at=NOW - timedelta(days=2))
    assert A.REOPEN not in compute_allowed_actions(context(REQUESTER, ticket), ticket, policy, NOW)
    ticket = make_ticket(S.RESOLVED, resolved_at=NOW - timedelta(hours=12), reopen_count=1)
    assert A.REOPEN not in compute_allowed_actions(context(REQUESTER, ticket), ticket, policy, NOW)
    ticket = make_ticket(S.RESOLVED, resolved_at=NOW - timedelta(hours=12))
    assert A.REOPEN in compute_allowed_actions(context(REQUESTER, ticket), ticket, policy, NOW)


@pytest.mark.parametrize(
    ("action", "actor", "status", "expected"),
    [
        (A.ACKNOWLEDGE, REQUESTER, S.NEW, ErrorCode.FORBIDDEN),
        (A.ACKNOWLEDGE, REQUESTER_SPOKE, S.NEW, ErrorCode.FORBIDDEN),
        (A.RESOLVE, REQUESTER_SPOKE, S.IN_PROGRESS, ErrorCode.FORBIDDEN),
        (A.ACKNOWLEDGE, SPOKE, S.IN_PROGRESS, ErrorCode.INVALID_TRANSITION),
        (A.CANCEL, REQUESTER, S.IN_PROGRESS, ErrorCode.INVALID_TRANSITION),
        (A.CONFIRM_CLOSURE, REQUESTER, S.IN_PROGRESS, ErrorCode.INVALID_TRANSITION),
        (A.CONFIRM_CLOSURE, SPOKE, S.RESOLVED, ErrorCode.FORBIDDEN),
        (A.INTERNAL_NOTE, COLLABORATOR, S.IN_PROGRESS, ErrorCode.FORBIDDEN),
        (A.COMMENT, COLLABORATOR, S.CLOSED, ErrorCode.INVALID_TRANSITION),
        (A.ASSIGN, ASSIGNEE, S.IN_PROGRESS, ErrorCode.FORBIDDEN),
        (A.RESOLVE, ASSIGNEE, S.NEW, ErrorCode.INVALID_TRANSITION),
        (A.TRANSFER, ADMIN, S.RESOLVED, ErrorCode.INVALID_TRANSITION),
        (A.COMMENT, UNRELATED, S.NEW, ErrorCode.FORBIDDEN),
        (A.COMMENT, OTHER_SPOKE, S.NEW, ErrorCode.FORBIDDEN),
    ],
)
def test_classify_denial(
    action: TicketAction, actor: Actor, status: TicketStatus, expected: ErrorCode
) -> None:
    requester = REQUESTER_SPOKE if actor is REQUESTER_SPOKE else REQUESTER
    ticket = make_ticket(status, requester=requester)
    assert classify_denial(action, context(actor, ticket), ticket) is expected


def test_classify_denial_reopen_outside_window_is_invalid_transition() -> None:
    ticket = make_ticket(S.CLOSED, resolved_at=NOW - timedelta(days=30))
    ctx = context(REQUESTER, ticket)
    assert A.REOPEN not in compute_allowed_actions(ctx, ticket, POLICY, NOW)
    assert classify_denial(A.REOPEN, ctx, ticket) is ErrorCode.INVALID_TRANSITION


def test_classify_denial_confidential_without_grant_is_forbidden() -> None:
    ticket = make_ticket(S.NEW, confidential=True)
    assert classify_denial(A.ACKNOWLEDGE, context(SPOKE, ticket), ticket) is ErrorCode.FORBIDDEN
    assert classify_denial(A.ACKNOWLEDGE, context(ADMIN, ticket), ticket) is ErrorCode.FORBIDDEN
