from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OutgoingEmail:
    to_address: str
    subject: str
    body_text: str
    body_html: str


class EmailSender(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...
