import uuid

import pytest

from app.core.enums import Priority, TicketStatus
from app.core.types import JsonObject
from app.models import Ticket
from app.services.email_templates import NOTIFICATION_SUBJECTS, SUBJECTS, render_email
from app.services.notifications import CONFIDENTIAL_TEMPLATE, ticket_message

BASE = "https://helpdesk.ibotix.ai"
TITLE = "Secret merger with Acme"
SECRET_BODY = "Board approved the offer"
TICKET_NO = "IBX-HR-2026-000042"

TICKET_KINDS: dict[str, JsonObject] = {
    "ticket_created": {},
    "ticket_acknowledged": {"owner": "Sam", "eta": "28 Oct 2026, 10:00 IST", "next_update": None},
    "ticket_assigned": {},
    "status_changed": {},
    "comment_added": {"author": "Sam", "body": SECRET_BODY},
    "eta_changed": {"old_eta": "a", "new_eta": "b", "is_extension": True},
    "transferred": {},
    "resolved": {"summary": SECRET_BODY},
    "closed": {},
    "reopened": {},
    "cancelled": {},
    "collaborator_added": {},
    "sla_warning": {"timer": "initial response", "level": 1},
    "escalation": {"timer": "initial response", "level": 2},
    "requester_reminder": {},
    "hold_review_due": {},
}

ACCOUNT_KINDS: dict[str, JsonObject] = {
    "signup_pending": {
        "applicant": "Asha",
        "applicant_email": "asha@ibotix.ai",
        "requested_role": "admin",
        "department": "IT",
    },
    "user_deactivated_open_tickets": {"user_name": "Ravi", "open_ticket_count": 3},
    "protected_action_requested": {"requester": "Sue", "target": "Tom", "action": "demote"},
    "protected_action_decided": {"target": "Tom", "action": "demote", "status": "approved"},
    "confidential_grant_changed": {"category": "Investigations", "granted": True},
    "notification_digest": {
        "date": "29 Oct 2026",
        "count": 2,
        "items": [
            {"text": f"Update on {TICKET_NO}", "ticket_id": TICKET_NO},
            {"text": "A signup request needs your approval", "ticket_id": None},
        ],
        "more": 0,
    },
}


def ticket(confidential: bool) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        ticket_no=TICKET_NO,
        department_id="HR",
        title=TITLE,
        description="Full details of the merger",
        priority=Priority.HIGH,
        status=TicketStatus.IN_PROGRESS,
        confidential=confidential,
        resolution_summary=SECRET_BODY,
    )


def render(template: str, context: JsonObject) -> str:
    rendered = render_email(template, {**context, "name": "Asha", "frontend_base_url": BASE})
    return "\n".join((rendered.subject, rendered.body_text, rendered.body_html))


def test_every_notification_template_has_a_case() -> None:
    assert set(TICKET_KINDS) | set(ACCOUNT_KINDS) | {CONFIDENTIAL_TEMPLATE} == set(
        NOTIFICATION_SUBJECTS
    )
    assert not set(NOTIFICATION_SUBJECTS) & set(SUBJECTS)


@pytest.mark.parametrize(("kind", "extras"), TICKET_KINDS.items())
def test_confidential_email_is_masked(kind: str, extras: JsonObject) -> None:
    message = ticket_message(ticket(True), kind=kind, text=f"{TITLE} changed", extras=extras)
    assert message.text == f"Update on {TICKET_NO}"
    assert message.template == CONFIDENTIAL_TEMPLATE
    assert set(message.context) == {"ticket_id", "department", "status", "priority"}
    assert message.template is not None
    content = render(message.template, message.context)
    assert TITLE not in content
    assert SECRET_BODY not in content
    assert "merger" not in content
    for fragment in (TICKET_NO, "HR", "in progress", "high", f"{BASE}/tickets/{TICKET_NO}"):
        assert fragment in content


@pytest.mark.parametrize(("kind", "extras"), TICKET_KINDS.items())
def test_regular_email_has_details(kind: str, extras: JsonObject) -> None:
    text = f"Ticket {TICKET_NO} update"
    message = ticket_message(ticket(False), kind=kind, text=text, extras=extras)
    assert message.text == text
    assert message.template == kind
    content = render(kind, message.context)
    for fragment in (TITLE, text, TICKET_NO, f"{BASE}/tickets/{TICKET_NO}"):
        assert fragment in content


def test_portal_only_message_has_no_template() -> None:
    message = ticket_message(ticket(True), kind="internal_note", text=TITLE, email=False)
    assert message.template is None
    assert message.text == f"Update on {TICKET_NO}"


def test_comment_and_resolution_only_in_regular_email() -> None:
    comment = ticket_message(
        ticket(False),
        kind="comment_added",
        text="New comment",
        extras=TICKET_KINDS["comment_added"],
    )
    assert SECRET_BODY in render("comment_added", comment.context)
    resolved = ticket_message(
        ticket(False), kind="resolved", text="Resolved", extras=TICKET_KINDS["resolved"]
    )
    assert SECRET_BODY in render("resolved", resolved.context)


def test_eta_wording() -> None:
    extended = render(
        "eta_changed",
        ticket_message(
            ticket(False), kind="eta_changed", text="ETA", extras=TICKET_KINDS["eta_changed"]
        ).context,
    )
    assert "The ETA was extended from a to b." in extended
    first = ticket_message(
        ticket(False),
        kind="eta_changed",
        text="ETA",
        extras={"old_eta": None, "new_eta": "b", "is_extension": False},
    )
    assert "The ETA was changed to b." in render("eta_changed", first.context)


@pytest.mark.parametrize(("kind", "context"), ACCOUNT_KINDS.items())
def test_account_notification_templates(kind: str, context: JsonObject) -> None:
    content = render(kind, context)
    assert "Hello Asha," in content
    assert f"{BASE}/login" in content
