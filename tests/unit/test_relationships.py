import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.enums import AccountState, Role, TicketStatus
from app.policy import Actor
from app.policy.actors import load_actor
from app.policy.relationships import load_relationship, relationship_from
from tests.factories import (
    FACTORY_NOW,
    make_category,
    make_collaborator,
    make_confidential_grant,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_user,
)


def test_load_actor_reads_role_and_active_spoke_mappings(db: Session) -> None:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    fin = make_department(db, "FIN")
    user = make_user(db, hr, role=Role.ADMIN)
    make_spoke_assignment(db, user, it)
    make_spoke_assignment(db, user, fin, revoked_at=FACTORY_NOW)
    actor = load_actor(db, user.id)
    assert actor == Actor(
        id=user.id,
        global_role=Role.ADMIN,
        department_id="HR",
        spoke_department_ids=frozenset({"IT"}),
        name=user.name,
        email=user.email,
    )


@pytest.mark.parametrize(
    "state",
    [
        AccountState.PENDING_VERIFICATION,
        AccountState.PENDING_APPROVAL,
        AccountState.REJECTED,
        AccountState.DEACTIVATED,
    ],
)
def test_load_actor_ignores_inactive_users(db: Session, state: AccountState) -> None:
    user = make_user(db, make_department(db, "IT"), state=state)
    assert load_actor(db, user.id) is None


def test_load_actor_unknown_user(db: Session) -> None:
    assert load_actor(db, uuid.uuid4()) is None


def test_relationship_flags_for_participants(db: Session) -> None:
    it = make_department(db, "IT")
    requester = make_user(db, it)
    owner = make_user(db, it)
    assignee = make_user(db, it)
    collaborator = make_user(db, it)
    secret = make_category(db, it, is_confidential=True)
    ticket = make_ticket(
        db,
        requester,
        it,
        status=TicketStatus.ASSIGNED,
        category=secret,
        owner=owner,
        assignee=assignee,
    )
    make_collaborator(db, ticket, collaborator)
    make_confidential_grant(db, collaborator, secret)

    def ctx(user_id: uuid.UUID) -> tuple[bool, ...]:
        actor = load_actor(db, user_id)
        assert actor is not None
        rel = load_relationship(db, actor, ticket)
        return (
            rel.is_requester,
            rel.is_owner,
            rel.is_assignee,
            rel.is_collaborator,
            rel.has_grant,
        )

    assert ctx(requester.id) == (True, False, False, False, False)
    assert ctx(owner.id) == (False, True, False, False, False)
    assert ctx(assignee.id) == (False, False, True, False, False)
    assert ctx(collaborator.id) == (False, False, False, True, True)


def test_relationship_department_spoke_and_roles(db: Session) -> None:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    requester = make_user(db, hr)
    spoke = make_user(db, hr)
    make_spoke_assignment(db, spoke, it)
    other_spoke = make_user(db, it)
    make_spoke_assignment(db, other_spoke, hr)
    admin = make_user(db, hr, role=Role.ADMIN)
    super_admin = make_user(db, hr, role=Role.SUPER_ADMIN)
    ticket = make_ticket(db, requester, it)
    expectations = {
        spoke.id: (True, False, False, False),
        other_spoke.id: (False, False, False, False),
        admin.id: (False, True, False, False),
        super_admin.id: (False, False, True, True),
    }
    for user_id, expected in expectations.items():
        actor = load_actor(db, user_id)
        assert actor is not None
        rel = load_relationship(db, actor, ticket)
        assert (
            rel.is_department_spoke,
            rel.is_admin,
            rel.is_super_admin,
            rel.has_confidential_access,
        ) == expected


def test_revoked_grant_gives_no_access(db: Session) -> None:
    it = make_department(db, "IT")
    user = make_user(db, it)
    secret = make_category(db, it, is_confidential=True)
    make_confidential_grant(db, user, secret, revoked_at=FACTORY_NOW)
    ticket = make_ticket(db, make_user(db, it), it, category=secret)
    actor = load_actor(db, user.id)
    assert actor is not None
    rel = load_relationship(db, actor, ticket)
    assert rel.has_grant is False
    assert rel.has_confidential_access is False


def test_uncategorized_ticket_has_no_grant(db: Session) -> None:
    it = make_department(db, "IT")
    user = make_user(db, it)
    make_confidential_grant(db, user, make_category(db, it, is_confidential=True))
    ticket = make_ticket(db, make_user(db, it), it, confidential=True)
    actor = load_actor(db, user.id)
    assert actor is not None
    assert load_relationship(db, actor, ticket).has_grant is False


def test_relationship_from_matches_loaded(db: Session) -> None:
    it = make_department(db, "IT")
    user = make_user(db, it)
    secret = make_category(db, it, is_confidential=True)
    make_confidential_grant(db, user, secret)
    ticket = make_ticket(db, make_user(db, it), it, category=secret)
    make_collaborator(db, ticket, user)
    actor = load_actor(db, user.id)
    assert actor is not None
    assert load_relationship(db, actor, ticket) == relationship_from(
        actor, ticket, {user.id}, {secret.id}, frozenset()
    )
    assert relationship_from(actor, ticket, set(), set(), set()).is_collaborator is False
