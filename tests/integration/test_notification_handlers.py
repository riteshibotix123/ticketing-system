import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    Priority,
    ProtectedActionKind,
    ProtectedActionStatus,
    Role,
    TicketStatus,
)
from app.core.events import (
    CollaboratorChanged,
    CommentAdded,
    ConfidentialGrantChanged,
    DomainEvent,
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
    TicketEtaChanged,
    TicketPriorityChanged,
    TicketReopened,
    TicketResolved,
    TicketStatusChanged,
    TicketTransferred,
    UserDeactivated,
)
from app.models import (
    CloseReason,
    EmailOutbox,
    Notification,
    Ticket,
    TicketEventKind,
    TimerKind,
    User,
)
from app.services.handlers import register_all
from tests.factories import (
    FACTORY_NOW,
    TicketWorld,
    make_protected_action,
    make_signup_request,
    make_ticket_event,
    make_ticket_world,
    make_timer,
    make_user,
)

NOW = FACTORY_NOW + timedelta(hours=6)

type Channels = dict[str, bool]


@pytest.fixture
def bus() -> EventBus:
    target = EventBus()
    register_all(target)
    return target


@pytest.fixture
def world(db: Session) -> TicketWorld:
    return make_ticket_world(db)


def emit(db: Session, bus: EventBus, event: DomainEvent) -> None:
    bus.publish(db, event)
    db.flush()


def names(world: TicketWorld) -> dict[uuid.UUID, str]:
    labels = {user.id: name for name, user in world.users.items()}
    for ticket in world.tickets.values():
        if ticket.owner_id is not None and ticket.owner_id not in labels:
            labels[ticket.owner_id] = "owner"
    return labels


def delivered(db: Session, world: TicketWorld, kind: str) -> Channels:
    labels = names(world)
    rows = list(db.scalars(select(Notification).where(Notification.kind == kind)))
    emailed = set(db.scalars(select(EmailOutbox.notification_id)))
    return {labels.get(row.user_id, str(row.user_id)): row.id in emailed for row in rows}


def only(db: Session, kind: str) -> Notification:
    row = db.scalars(select(Notification).where(Notification.kind == kind)).first()
    assert row is not None
    return row


def outbox_for(db: Session, notification: Notification) -> EmailOutbox:
    row = db.scalars(
        select(EmailOutbox).where(EmailOutbox.notification_id == notification.id)
    ).first()
    assert row is not None
    return row


def test_ticket_created(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    requester = world.users["requester"]
    emit(db, bus, TicketCreated(actor_id=requester.id, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "ticket_created") == {"spoke": True, "spoke_with_grant": True}
    notification = only(db, "ticket_created")
    assert notification.text == f"New ticket {ticket.ticket_no} in IT: Laptop screen flickers"
    assert notification.ticket_id == ticket.id
    assert notification.critical is False
    assert notification.created_at == NOW
    email = outbox_for(db, notification)
    assert email.template == "ticket_created"
    assert "Laptop screen flickers" in email.body_text


def test_confidential_ticket_created_is_filtered_and_masked(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["secret"]
    requester = world.users["requester"]
    emit(db, bus, TicketCreated(actor_id=requester.id, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "ticket_created") == {"spoke_with_grant": True}
    notification = only(db, "ticket_created")
    assert notification.text == f"Update on {ticket.ticket_no}"
    email = outbox_for(db, notification)
    assert email.template == "confidential_ticket_update"
    for content in (email.subject, email.body_text, email.body_html, str(email.context)):
        assert "Sensitive matter" not in content
        assert ticket.description not in content
    assert ticket.ticket_no in email.body_text


def test_acknowledged(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    owner = db.get(User, ticket.owner_id)
    assert owner is not None
    emit(db, bus, TicketAcknowledged(actor_id=owner.id, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "ticket_acknowledged") == {"requester": True}
    text = only(db, "ticket_acknowledged").text
    assert text.startswith(f"Your ticket {ticket.ticket_no} was acknowledged by {owner.name}.")
    assert "ETA 29 Oct 2026" in text


def test_assigned(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    spoke = world.users["spoke"]
    emit(db, bus, TicketAssigned(actor_id=spoke.id, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "ticket_assigned") == {
        "assignee": True,
        "requester": False,
        "spoke_with_grant": False,
    }


def test_status_changed(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    emit(
        db,
        bus,
        TicketStatusChanged(
            actor_id=world.users["spoke"].id,
            occurred_at=NOW,
            ticket_id=ticket.id,
            from_status=TicketStatus.ASSIGNED,
            to_status=TicketStatus.IN_PROGRESS,
        ),
    )
    assert delivered(db, world, "status_changed") == {
        "requester": True,
        "assignee": False,
    }
    assert only(db, "status_changed").text == f"Ticket {ticket.ticket_no} is now in progress"


def comment_event(
    db: Session, world: TicketWorld, author: str, *, internal: bool = False
) -> CommentAdded:
    ticket = world.tickets["normal"]
    user = world.users[author]
    row = make_ticket_event(
        db,
        ticket,
        actor=user,
        kind=TicketEventKind.INTERNAL_NOTE if internal else TicketEventKind.COMMENT,
        action=None,
        body="Please restart the laptop",
        is_public=not internal,
    )
    return CommentAdded(
        actor_id=user.id,
        occurred_at=NOW,
        ticket_id=ticket.id,
        ticket_event_id=row.id,
        internal=internal,
    )


def test_team_comment_goes_to_requester_and_collaborators(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    emit(db, bus, comment_event(db, world, "assignee"))
    assert delivered(db, world, "comment_added") == {"requester": True, "collaborator": True}
    email = outbox_for(db, only(db, "comment_added"))
    assert "Please restart the laptop" in email.body_text


@pytest.mark.parametrize("author", ["requester", "collaborator"])
def test_participant_comment_goes_to_team(
    db: Session, bus: EventBus, world: TicketWorld, author: str
) -> None:
    emit(db, bus, comment_event(db, world, author))
    expected = {"assignee": True, "spoke": True, "spoke_with_grant": True}
    assert delivered(db, world, "comment_added") == expected


def test_internal_note_is_portal_only_for_team(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    emit(db, bus, comment_event(db, world, "spoke", internal=True))
    assert delivered(db, world, "internal_note") == {
        "assignee": False,
        "spoke_with_grant": False,
    }
    assert delivered(db, world, "comment_added") == {}


def test_eta_changed(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    emit(
        db,
        bus,
        TicketEtaChanged(
            actor_id=world.users["assignee"].id,
            occurred_at=NOW,
            ticket_id=ticket.id,
            old=FACTORY_NOW + timedelta(days=1),
            new=FACTORY_NOW + timedelta(days=3),
            is_extension=True,
            reason="Vendor delay",
        ),
    )
    assert delivered(db, world, "eta_changed") == {"requester": True}
    notification = only(db, "eta_changed")
    assert notification.text.startswith(f"ETA for {ticket.ticket_no} extended from")
    email = outbox_for(db, notification)
    assert "The ETA was extended" in email.body_text
    assert "Vendor delay" not in email.body_text


def test_priority_changed(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    emit(
        db,
        bus,
        TicketPriorityChanged(
            actor_id=world.users["admin"].id,
            occurred_at=NOW,
            ticket_id=ticket.id,
            old=Priority.MEDIUM,
            new=Priority.HIGH,
        ),
    )
    assert delivered(db, world, "priority_changed") == {"assignee": False}


def test_transferred_notifies_only_visible_spokes(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["normal"]
    ticket.department_id = "HR"
    ticket.category_id = None
    db.flush()
    emit(
        db,
        bus,
        TicketTransferred(
            actor_id=world.users["spoke"].id,
            occurred_at=NOW,
            ticket_id=ticket.id,
            from_department="IT",
            to_department="HR",
        ),
    )
    assert delivered(db, world, "transferred") == {"requester": True, "other_spoke": True}


def test_resolved(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    ticket.status = TicketStatus.RESOLVED
    ticket.resolution_summary = "Replaced the display cable"
    db.flush()
    actor = world.users["assignee"].id
    emit(db, bus, TicketResolved(actor_id=actor, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "resolved") == {"requester": True}
    email = outbox_for(db, only(db, "resolved"))
    assert "Replaced the display cable" in email.body_text
    assert "confirm the resolution or reopen" in email.body_text


def test_closed_by_system(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    emit(
        db,
        bus,
        TicketClosed(actor_id=None, occurred_at=NOW, ticket_id=ticket.id, reason=CloseReason.AUTO),
    )
    assert delivered(db, world, "closed") == {
        "requester": True,
        "assignee": False,
    }


def test_reopened(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    actor = world.users["requester"].id
    emit(db, bus, TicketReopened(actor_id=actor, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "reopened") == {
        "assignee": True,
        "spoke": True,
        "spoke_with_grant": True,
    }


def test_reopened_by_team_notifies_requester_in_portal(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["normal"]
    actor = world.users["spoke"].id
    emit(db, bus, TicketReopened(actor_id=actor, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "reopened")["requester"] is False


def test_cancelled(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    actor = world.users["admin"].id
    emit(db, bus, TicketCancelled(actor_id=actor, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "cancelled") == {
        "requester": True,
        "assignee": False,
    }


def test_collaborator_added_and_removed(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    collaborator = world.users["collaborator"]
    for added in (True, False):
        emit(
            db,
            bus,
            CollaboratorChanged(
                actor_id=world.users["spoke"].id,
                occurred_at=NOW,
                ticket_id=ticket.id,
                user_id=collaborator.id,
                added=added,
            ),
        )
    assert delivered(db, world, "collaborator_added") == {"collaborator": True}


def test_sla_warning_is_deduplicated(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    make_timer(db, ticket, TimerKind.PROGRESS_UPDATE, cycle=2)
    event = SlaWarningRaised(
        actor_id=None,
        occurred_at=NOW,
        ticket_id=ticket.id,
        timer_kind=TimerKind.PROGRESS_UPDATE,
        level=1,
    )
    emit(db, bus, event)
    emit(db, bus, event)
    expected = {"assignee": True, "spoke": True, "spoke_with_grant": True}
    assert delivered(db, world, "sla_warning") == expected
    notification = only(db, "sla_warning")
    assert notification.critical is False
    assert notification.dedupe_key == f"sla_warning:{ticket.id}:progress_update:2:L1"
    assert notification.text == f"L1 progress update warning on {ticket.ticket_no}"
    assert db.scalar(select(func.count()).select_from(EmailOutbox)) == len(expected)


def escalation(ticket: Ticket, level: int, step_key: str) -> EscalationRaised:
    return EscalationRaised(
        actor_id=None,
        occurred_at=NOW,
        ticket_id=ticket.id,
        timer_kind=TimerKind.INITIAL_RESPONSE,
        level=level,
        step_key=step_key,
    )


def test_l2_escalation_is_critical_and_deduplicated(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["normal"]
    timer = make_timer(db, ticket)
    emit(db, bus, escalation(ticket, 2, "L2"))
    emit(db, bus, escalation(ticket, 2, "L2"))
    expected = {
        "assignee": True,
        "spoke": True,
        "spoke_with_grant": True,
        "admin": True,
        "admin_with_grant": True,
    }
    assert delivered(db, world, "escalation") == expected
    notification = only(db, "escalation")
    assert notification.critical is True
    assert notification.text == f"L2 initial response breach on {ticket.ticket_no}"
    timer.cycle = 2
    db.flush()
    emit(db, bus, escalation(ticket, 2, "L2"))
    count = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.kind == "escalation")
    )
    assert count == 2 * len(expected)


def test_l1_escalation_is_left_to_the_warning(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    emit(db, bus, escalation(world.tickets["normal"], 1, "L1"))
    assert delivered(db, world, "escalation") == {}


def test_creation_contact_falls_back_to_admins(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["normal"]
    emit(db, bus, escalation(ticket, 1, "CREATION_CONTACT"))
    assert delivered(db, world, "escalation") == {"admin": True, "admin_with_grant": True}
    notification = only(db, "escalation")
    assert notification.critical is True
    assert notification.text.startswith(f"Critical ticket {ticket.ticket_no} raised in IT")


def test_confidential_escalation_skips_admin_and_spoke_without_grant(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["secret"]
    emit(db, bus, escalation(ticket, 2, "L2"))
    assert delivered(db, world, "escalation") == {
        "assignee": True,
        "spoke_with_grant": True,
        "admin_with_grant": True,
    }
    notification = only(db, "escalation")
    assert notification.text == f"Update on {ticket.ticket_no}"
    email = outbox_for(db, notification)
    assert "Sensitive matter" not in email.body_text + email.body_html + email.subject


def test_owner_without_visibility_is_skipped(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["normal"]
    owner = ticket.owner_id
    assert owner is not None
    emit(db, bus, TicketCancelled(actor_id=None, occurred_at=NOW, ticket_id=ticket.id))
    assert "owner" not in delivered(db, world, "cancelled")
    ticket.owner_id = world.users["spoke"].id
    ticket.status = TicketStatus.REOPENED
    db.flush()
    emit(db, bus, TicketReopened(actor_id=None, occurred_at=NOW, ticket_id=ticket.id))
    assert delivered(db, world, "reopened")["spoke"] is True


def test_confidential_status_change_skips_owner_without_access(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["secret"]
    emit(
        db,
        bus,
        TicketStatusChanged(
            actor_id=world.users["spoke_with_grant"].id,
            occurred_at=NOW,
            ticket_id=ticket.id,
            from_status=TicketStatus.ASSIGNED,
            to_status=TicketStatus.IN_PROGRESS,
        ),
    )
    assert delivered(db, world, "status_changed") == {"requester": True, "assignee": False}


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (Role.EMPLOYEE, {"admin": True, "admin_with_grant": True, "super_admin": True}),
        (Role.ADMIN, {"super_admin": True}),
        (Role.SUPER_ADMIN, {"super_admin": True}),
    ],
)
def test_signup_verified(
    db: Session, bus: EventBus, world: TicketWorld, role: Role, expected: dict[str, bool]
) -> None:
    applicant = make_user(db, world.it, name="Asha Applicant")
    request = make_signup_request(db, applicant, world.it, requested_role=role)
    emit(
        db,
        bus,
        SignupVerified(actor_id=applicant.id, occurred_at=NOW, signup_request_id=request.id),
    )
    assert delivered(db, world, "signup_pending") == expected
    notification = only(db, "signup_pending")
    assert notification.ticket_id is None
    assert notification.critical is False
    assert "Asha Applicant" in notification.text


def test_user_deactivated(db: Session, bus: EventBus, world: TicketWorld) -> None:
    target = world.users["unrelated"]
    actor = world.users["admin"]
    for count in (0, 2):
        emit(
            db,
            bus,
            UserDeactivated(
                actor_id=actor.id, occurred_at=NOW, user_id=target.id, open_ticket_count=count
            ),
        )
    assert delivered(db, world, "user_deactivated_open_tickets") == {
        "admin_with_grant": True,
        "super_admin": True,
    }
    notification = only(db, "user_deactivated_open_tickets")
    assert notification.critical is True
    assert notification.text == "Unrelated was deactivated with 2 open tickets"


def test_protected_actions(db: Session, bus: EventBus, world: TicketWorld) -> None:
    requester = world.users["super_admin"]
    target = make_user(db, world.hr, role=Role.SUPER_ADMIN, name="Tom Target")
    decider = make_user(db, world.hr, role=Role.SUPER_ADMIN, name="Dee Decider")
    request = make_protected_action(
        db, target, requester, kind=ProtectedActionKind.DEMOTE_SUPER_ADMIN
    )
    emit(
        db,
        bus,
        ProtectedActionRequested(
            actor_id=requester.id, occurred_at=NOW, protected_action_id=request.id
        ),
    )
    requested = list(
        db.scalars(select(Notification).where(Notification.kind == "protected_action_requested"))
    )
    assert [row.user_id for row in requested] == [decider.id]
    assert requested[0].critical is True
    assert requested[0].text == "Super Admin requested to demote Super Admin Tom Target"
    request.status = ProtectedActionStatus.APPROVED
    db.flush()
    emit(
        db,
        bus,
        ProtectedActionDecided(
            actor_id=decider.id, occurred_at=NOW, protected_action_id=request.id
        ),
    )
    decided = list(
        db.scalars(select(Notification).where(Notification.kind == "protected_action_decided"))
    )
    assert {row.user_id for row in decided} == {requester.id, target.id}
    assert all(row.critical for row in decided)
    assert decided[0].text == "The request to demote Super Admin Tom Target was approved"


def test_confidential_grant_changed(db: Session, bus: EventBus, world: TicketWorld) -> None:
    user = world.users["employee_with_grant"]
    actor = world.users["super_admin"]
    emit(
        db,
        bus,
        ConfidentialGrantChanged(
            actor_id=actor.id,
            occurred_at=NOW,
            user_id=user.id,
            category_id=world.secret_category.id,
        ),
    )
    assert delivered(db, world, "confidential_grant_changed") == {"employee_with_grant": True}
    text = only(db, "confidential_grant_changed").text
    assert text == "You were granted access to confidential category Investigations"


def test_acting_user_is_never_notified(db: Session, bus: EventBus, world: TicketWorld) -> None:
    ticket = world.tickets["normal"]
    actor = world.users["spoke"]
    emit(db, bus, TicketCreated(actor_id=actor.id, occurred_at=NOW, ticket_id=ticket.id))
    assert "spoke" not in delivered(db, world, "ticket_created")


def test_notifications_and_outbox_share_the_event_transaction(
    db: Session, bus: EventBus, world: TicketWorld
) -> None:
    ticket = world.tickets["normal"]
    emit(
        db,
        bus,
        TicketCreated(actor_id=world.users["requester"].id, occurred_at=NOW, ticket_id=ticket.id),
    )
    notification = only(db, "ticket_created")
    assert outbox_for(db, notification).notification_id == notification.id
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Notification)) == 0
    assert db.scalar(select(func.count()).select_from(EmailOutbox)) == 0
