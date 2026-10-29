from dataclasses import dataclass

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AccountState, Role, TicketStatus
from app.models import Category, Department, EscalationEvent, Ticket, TimerKind, User
from app.services.sla.escalation import record_step, resolve_recipients
from tests.factories import (
    FACTORY_NOW,
    make_category,
    make_confidential_grant,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_user,
)


@dataclass
class Org:
    it: Department
    owner: User
    assignee: User
    spoke: User
    inactive_spoke: User
    contact: User
    admin: User
    super_admin: User
    requester: User


@pytest.fixture
def org(db: Session) -> Org:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    owner = make_user(db, it, name="Owner")
    assignee = make_user(db, it, name="Assignee")
    spoke = make_user(db, hr, name="Spoke")
    inactive_spoke = make_user(db, hr, name="Inactive", state=AccountState.DEACTIVATED)
    for user in (owner, spoke, inactive_spoke):
        make_spoke_assignment(db, user, it)
    contact = make_user(db, it, name="Contact")
    it.escalation_contact_user_id = contact.id
    admin = make_user(db, hr, name="Admin", role=Role.ADMIN)
    super_admin = make_user(db, hr, name="Super", role=Role.SUPER_ADMIN)
    make_user(db, hr, name="Former Admin", role=Role.ADMIN, state=AccountState.DEACTIVATED)
    requester = make_user(db, hr, name="Requester")
    db.flush()
    return Org(it, owner, assignee, spoke, inactive_spoke, contact, admin, super_admin, requester)


def ticket_for(db: Session, org: Org, *, confidential: bool = False) -> Ticket:
    category = make_category(db, org.it, is_confidential=confidential)
    return make_ticket(
        db,
        org.requester,
        org.it,
        status=TicketStatus.IN_PROGRESS,
        category=category,
        owner=org.owner,
        assignee=org.assignee,
    )


def names(users: list[User]) -> set[str]:
    return {user.name for user in users}


def test_l1_is_owner_assignee_and_active_spokes(db: Session, org: Org) -> None:
    ticket = ticket_for(db, org)
    assert names(resolve_recipients(db, ticket, 1)) == {"Owner", "Assignee", "Spoke"}


def test_l2_adds_contact_and_admins(db: Session, org: Org) -> None:
    ticket = ticket_for(db, org)
    assert names(resolve_recipients(db, ticket, 2)) == {
        "Owner",
        "Assignee",
        "Spoke",
        "Contact",
        "Admin",
    }


@pytest.mark.parametrize("missing", ["none", "inactive"])
def test_l2_without_contact_falls_back_to_admins(db: Session, org: Org, missing: str) -> None:
    if missing == "none":
        org.it.escalation_contact_user_id = None
    else:
        org.contact.state = AccountState.DEACTIVATED
    db.flush()
    ticket = ticket_for(db, org)
    assert names(resolve_recipients(db, ticket, 2)) == {"Owner", "Assignee", "Spoke", "Admin"}


def test_l2_without_contact_or_admins_falls_back_to_super_admins(db: Session, org: Org) -> None:
    org.it.escalation_contact_user_id = None
    org.admin.state = AccountState.DEACTIVATED
    db.flush()
    ticket = ticket_for(db, org)
    assert names(resolve_recipients(db, ticket, 2)) == {"Owner", "Assignee", "Spoke", "Super"}


def test_l3_is_all_admins_and_super_admins(db: Session, org: Org) -> None:
    ticket = ticket_for(db, org)
    assert names(resolve_recipients(db, ticket, 3)) == {"Admin", "Super"}


def test_creation_contact_and_fallback_chain(db: Session, org: Org) -> None:
    ticket = ticket_for(db, org)
    assert names(resolve_recipients(db, ticket, 1, creation_contact=True)) == {"Contact"}
    org.it.escalation_contact_user_id = None
    db.flush()
    assert names(resolve_recipients(db, ticket, 1, creation_contact=True)) == {"Admin"}
    org.admin.state = AccountState.DEACTIVATED
    db.flush()
    assert names(resolve_recipients(db, ticket, 1, creation_contact=True)) == {"Super"}


def test_recipients_are_unique_and_sorted(db: Session, org: Org) -> None:
    org.it.escalation_contact_user_id = org.owner.id
    db.flush()
    ticket = ticket_for(db, org)
    recipients = resolve_recipients(db, ticket, 2)
    assert len(recipients) == len({user.id for user in recipients})
    assert [user.name for user in recipients] == sorted(user.name for user in recipients)


def test_confidential_filters_unauthorized_users(db: Session, org: Org) -> None:
    ticket = ticket_for(db, org, confidential=True)
    assert names(resolve_recipients(db, ticket, 1)) == {"Assignee"}
    assert names(resolve_recipients(db, ticket, 2)) == {"Assignee", "Super"}
    assert names(resolve_recipients(db, ticket, 3)) == {"Super"}
    assert names(resolve_recipients(db, ticket, 1, creation_contact=True)) == {"Super"}


def test_confidential_keeps_granted_users(db: Session, org: Org) -> None:
    ticket = ticket_for(db, org, confidential=True)
    category = db.get_one(Category, ticket.category_id)
    for user in (org.spoke, org.contact, org.admin):
        make_confidential_grant(db, user, category)
    assert names(resolve_recipients(db, ticket, 2)) == {"Assignee", "Spoke", "Contact", "Admin"}
    assert names(resolve_recipients(db, ticket, 3)) == {"Admin", "Super"}


def test_confidential_with_no_admins_still_reaches_super_admins(db: Session, org: Org) -> None:
    org.admin.state = AccountState.DEACTIVATED
    db.flush()
    ticket = ticket_for(db, org, confidential=True)
    assert "Super" in names(resolve_recipients(db, ticket, 2))


def test_record_step_is_idempotent(db: Session, org: Org) -> None:
    ticket = ticket_for(db, org)
    recipients = [org.owner.id, org.spoke.id]
    args = (db, ticket, TimerKind.INITIAL_RESPONSE)
    assert record_step(*args, 1, 2, "L2", FACTORY_NOW, recipients) is True
    assert record_step(*args, 1, 2, "L2", FACTORY_NOW, recipients) is False
    assert record_step(*args, 2, 2, "L2", FACTORY_NOW, recipients) is True
    assert record_step(*args, 1, 3, "L3", FACTORY_NOW, recipients) is True
    assert record_step(db, ticket, TimerKind.ETA, 1, 2, "L2", FACTORY_NOW, []) is True
    count = db.scalar(
        select(func.count())
        .select_from(EscalationEvent)
        .where(EscalationEvent.ticket_id == ticket.id)
    )
    assert count == 4
    stored = db.scalars(
        select(EscalationEvent).where(
            EscalationEvent.ticket_id == ticket.id, EscalationEvent.step_key == "L3"
        )
    ).one()
    assert stored.recipient_ids == recipients
    assert stored.timer_kind is TimerKind.INITIAL_RESPONSE
