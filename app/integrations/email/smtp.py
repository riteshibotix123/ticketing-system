import smtplib
from email.message import EmailMessage

from app.core.config import Settings
from app.integrations.email.base import OutgoingEmail

SMTP_TIMEOUT_SECONDS = 30


class SmtpSender:
    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._from = settings.smtp_from
        self._starttls = settings.smtp_starttls

    def send(self, message: OutgoingEmail) -> None:
        email = EmailMessage()
        email["From"] = self._from
        email["To"] = message.to_address
        email["Subject"] = message.subject
        email.set_content(message.body_text)
        email.add_alternative(message.body_html, subtype="html")
        with smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS) as client:
            if self._starttls:
                client.starttls()
            if self._user:
                client.login(self._user, self._password.get_secret_value())
            client.send_message(email)
