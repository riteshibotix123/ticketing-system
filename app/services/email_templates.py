from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.types import JsonObject

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "email"

SUBJECTS: dict[str, str] = {
    "verify_email": "Verify your email address",
    "account_exists_notice": "You already have an account",
    "signup_approved": "Your account has been approved",
    "signup_rejected": "Your signup request was not approved",
    "password_reset": "Reset your password",
}

NOTIFICATION_SUBJECTS: dict[str, str] = {
    "signup_pending": "A signup request needs your approval",
    "user_deactivated_open_tickets": "A deactivated user still has open tickets",
    "protected_action_requested": "A protected action needs your decision",
    "protected_action_decided": "A protected action was decided",
    "confidential_grant_changed": "Your confidential access changed",
    "ticket_created": "New ticket raised",
    "ticket_acknowledged": "Your ticket was acknowledged",
    "ticket_assigned": "Ticket assigned",
    "status_changed": "Ticket status changed",
    "comment_added": "New comment on a ticket",
    "eta_changed": "Ticket ETA changed",
    "transferred": "Ticket transferred",
    "resolved": "Your ticket was resolved",
    "closed": "Ticket closed",
    "reopened": "Ticket reopened",
    "cancelled": "Ticket cancelled",
    "collaborator_added": "You were added to a ticket",
    "sla_warning": "SLA warning on a ticket",
    "escalation": "Ticket escalation",
    "requester_reminder": "A ticket is waiting for your reply",
    "hold_review_due": "Hold review due on a ticket",
    "confidential_ticket_update": "Update on a confidential ticket",
    "notification_digest": "Your daily notification digest",
}

_environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(enabled_extensions=("html.j2",), default_for_string=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


class UnknownEmailTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    body_text: str
    body_html: str


def render_email(template: str, context: JsonObject) -> RenderedEmail:
    subject = SUBJECTS.get(template, NOTIFICATION_SUBJECTS.get(template))
    if subject is None:
        raise UnknownEmailTemplateError(template)
    return RenderedEmail(
        subject=subject,
        body_text=_environment.get_template(f"{template}.txt.j2").render(context),
        body_html=_environment.get_template(f"{template}.html.j2").render(context),
    )
