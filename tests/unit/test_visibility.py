from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Role, TicketStatus
from app.models import Ticket, User
from app.policy import Actor
from app.policy.actors import load_actor
from app.policy.visibility import can_view_ticket, visible_ticket_clause
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


@dataclass(frozen=True)
class World:
    users: dict[str, User]
    tickets: dict[str, Ticket]


ACTOR_NAMES = (
    "requester",
    "assignee",
    "collaborator",
    "spoke",
    "spoke_with_grant",
    "spoke_with_revoked_grant",
    "revoked_spoke",
    "other_spoke",
    "other_spoke_with_grant",
    "admin",
    "admin_with_grant",
    "super_admin",
    "employee_with_grant",
    "unrelated",
)


@pytest.fixture
def world(db: Session) -> World:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    users = {
        name: make_user(
            db,
            hr,
            role=Role.ADMIN
            if name.startswith("admin")
            else Role.SUPER_ADMIN
            if name == "super_admin"
            else Role.EMPLOYEE,
        )
        for name in ACTOR_NAMES
    }
    for name in ("spoke", "spoke_with_grant", "spoke_with_revoked_grant"):
        make_spoke_assignment(db, users[name], it)
    make_spoke_assignment(db, users["revoked_spoke"], it, revoked_at=FACTORY_NOW)
    for name in ("other_spoke", "other_spoke_with_grant"):
        make_spoke_assignment(db, users[name], hr)
    normal = make_category(db, it)
    secret = make_category(db, it, is_confidential=True)
    other_secret = make_category(db, it, is_confidential=True)
    for name in ("spoke_with_grant", "other_spoke_with_grant", "admin_with_grant"):
        make_confidential_grant(db, users[name], secret)
        make_confidential_grant(db, users[name], normal)
    make_confidential_grant(db, users["employee_with_grant"], secret)
    make_confidential_grant(db, users["spoke_with_revoked_grant"], secret, revoked_at=FACTORY_NOW)
    tickets = {
        "normal": make_ticket(
            db,
            users["requester"],
            it,
            status=TicketStatus.IN_PROGRESS,
            category=normal,
            assignee=users["assignee"],
        ),
        "confidential": make_ticket(
            db,
            users["requester"],
            it,
            status=TicketStatus.IN_PROGRESS,
            category=secret,
            assignee=users["assignee"],
        ),
        "confidential_other_category": make_ticket(
            db,
            users["requester"],
            it,
            status=TicketStatus.IN_PROGRESS,
            category=other_secret,
            assignee=users["assignee"],
        ),
        "confidential_flag_only": make_ticket(
            db, users["requester"], it, confidential=True, category=normal
        ),
        "uncategorized": make_ticket(db, users["requester"], it),
        "hr_normal": make_ticket(db, users["requester"], hr),
        "closed": make_ticket(db, users["requester"], it, status=TicketStatus.CLOSED),
    }
    for ticket in (tickets["normal"], tickets["confidential"]):
        make_collaborator(db, ticket, users["collaborator"])
    return World(users=users, tickets=tickets)


def actor_of(db: Session, user: User) -> Actor:
    actor = load_actor(db, user.id)
    assert actor is not None
    return actor


VISIBILITY: list[tuple[str, bool, bool]] = [
    ("requester", True, True),
    ("assignee", True, True),
    ("collaborator", True, True),
    ("spoke", True, False),
    ("spoke_with_grant", True, True),
    ("spoke_with_revoked_grant", True, False),
    ("revoked_spoke", False, False),
    ("other_spoke", False, False),
    ("other_spoke_with_grant", False, True),
    ("admin", True, False),
    ("admin_with_grant", True, True),
    ("super_admin", True, True),
    ("employee_with_grant", False, True),
    ("unrelated", False, False),
]


@pytest.mark.parametrize(
    ("name", "sees_normal", "sees_confidential"),
    VISIBILITY,
    ids=[name for name, *_ in VISIBILITY],
)
def test_visibility_by_actor_class(
    db: Session, world: World, name: str, sees_normal: bool, sees_confidential: bool
) -> None:
    actor = actor_of(db, world.users[name])
    assert can_view_ticket(db, actor, world.tickets["normal"]) is sees_normal
    assert can_view_ticket(db, actor, world.tickets["confidential"]) is sees_confidential


@pytest.mark.parametrize("name", ["spoke", "spoke_with_revoked_grant", "admin", "other_spoke"])
def test_confidential_never_visible_to_spoke_or_admin_without_grant(
    db: Session, world: World, name: str
) -> None:
    actor = actor_of(db, world.users[name])
    for key in ("confidential", "confidential_other_category", "confidential_flag_only"):
        assert can_view_ticket(db, actor, world.tickets[key]) is False
    visible = set(
        db.scalars(
            select(Ticket.ticket_no).where(visible_ticket_clause(actor), Ticket.confidential)
        )
    )
    assert visible == set()


def test_grant_applies_only_to_its_category(db: Session, world: World) -> None:
    actor = actor_of(db, world.users["spoke_with_grant"])
    assert can_view_ticket(db, actor, world.tickets["confidential"]) is True
    assert can_view_ticket(db, actor, world.tickets["confidential_other_category"]) is False
    assert can_view_ticket(db, actor, world.tickets["confidential_flag_only"]) is True


def test_other_department_spoke_sees_only_own_department(db: Session, world: World) -> None:
    actor = actor_of(db, world.users["other_spoke"])
    assert can_view_ticket(db, actor, world.tickets["hr_normal"]) is True
    assert can_view_ticket(db, actor, world.tickets["normal"]) is False


def test_super_admin_sees_everything(db: Session, world: World) -> None:
    actor = actor_of(db, world.users["super_admin"])
    ids = {ticket.id for ticket in world.tickets.values()}
    visible = set(db.scalars(select(Ticket.id).where(visible_ticket_clause(actor))))
    assert ids <= visible


@pytest.mark.parametrize("name", ACTOR_NAMES)
def test_clause_and_loaded_decision_agree(db: Session, world: World, name: str) -> None:
    actor = actor_of(db, world.users[name])
    ids = [ticket.id for ticket in world.tickets.values()]
    from_clause = set(
        db.scalars(select(Ticket.id).where(Ticket.id.in_(ids), visible_ticket_clause(actor)))
    )
    loaded = {ticket.id for ticket in world.tickets.values() if can_view_ticket(db, actor, ticket)}
    assert from_clause == loaded


def test_escalation_contact_sees_only_non_confidential_tickets_of_their_department(
    db: Session,
) -> None:
    hr = make_department(db, "QA")
    other = make_department(db, "OPS")
    contact = make_user(db, hr)
    hr.escalation_contact_user_id = contact.id
    requester = make_user(db, hr)
    secret = make_category(db, hr, is_confidential=True)
    normal = make_ticket(db, requester, hr)
    hidden = make_ticket(db, requester, hr, category=secret, confidential=True)
    elsewhere = make_ticket(db, requester, other)
    db.flush()
    actor = actor_of(db, contact)
    assert can_view_ticket(db, actor, normal)
    assert not can_view_ticket(db, actor, hidden)
    assert not can_view_ticket(db, actor, elsewhere)
    visible = set(db.scalars(select(Ticket.id).where(visible_ticket_clause(actor))))
    assert visible == {normal.id}
