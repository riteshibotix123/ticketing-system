from app.core.config import Environment, Settings
from app.integrations.email.base import EmailSender, OutgoingEmail
from app.integrations.email.memory import InMemorySender
from app.integrations.email.smtp import SmtpSender


def build_sender(settings: Settings) -> EmailSender:
    if settings.env is Environment.TEST:
        return InMemorySender()
    return SmtpSender(settings)


__all__ = ["EmailSender", "InMemorySender", "OutgoingEmail", "SmtpSender", "build_sender"]
