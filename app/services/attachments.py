import hashlib
import io
import os
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.enums import ScanStatus
from app.core.errors import file_too_large, not_found, unsupported_file_type, validation_error
from app.integrations.scanner import Scanner
from app.integrations.storage import Storage
from app.models.ticket import Attachment, Ticket
from app.policy import Actor
from app.policy.visibility import can_view_ticket
from app.schemas.attachments import AttachmentOut
from app.services.audit import AuditService
from app.services.ticket_reads import attachment_out

STORAGE_HINT: Final = "attachments"
MAX_NAME_LENGTH: Final = 150
DEFAULT_NAME: Final = "attachment"
FILE_FIELD: Final = "file"
OOXML_TYPES: Final = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)
TEXT_TYPES: Final = frozenset({"text/plain", "text/csv"})


def _is_utf8_text(content: bytes) -> bool:
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


SNIFFERS: Final[dict[str, Callable[[bytes], bool]]] = {
    "application/pdf": lambda content: content.startswith(b"%PDF-"),
    "image/png": lambda content: content.startswith(b"\x89PNG"),
    "image/jpeg": lambda content: content.startswith(b"\xff\xd8\xff"),
    **{media: (lambda content: content.startswith(b"PK\x03\x04")) for media in OOXML_TYPES},
    **dict.fromkeys(TEXT_TYPES, _is_utf8_text),
}


def normalize_content_type(declared: str | None) -> str:
    if not declared:
        return ""
    return declared.split(";", 1)[0].strip().lower()


def content_matches(content_type: str, content: bytes) -> bool:
    sniffer = SNIFFERS.get(content_type)
    return sniffer is not None and sniffer(content)


def sanitize_file_name(raw: str | None) -> str:
    base = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(
        char for char in base if not unicodedata.category(char).startswith("C")
    ).strip()
    cleaned = cleaned.lstrip(".").strip()
    if not cleaned:
        return DEFAULT_NAME
    if len(cleaned) <= MAX_NAME_LENGTH:
        return cleaned
    stem, extension = os.path.splitext(cleaned)
    if 0 < len(extension) < MAX_NAME_LENGTH // 2:
        return stem[: MAX_NAME_LENGTH - len(extension)] + extension
    return cleaned[:MAX_NAME_LENGTH]


@dataclass(frozen=True, slots=True)
class Download:
    attachment: Attachment
    stream: BinaryIO


class AttachmentService:
    def __init__(
        self,
        session: Session,
        clock: Clock,
        settings: Settings,
        storage: Storage,
        scanner: Scanner,
    ) -> None:
        self._session = session
        self._clock = clock
        self._settings = settings
        self._storage = storage
        self._scanner = scanner
        self._audit = AuditService(session, clock)

    def upload(
        self,
        actor: Actor,
        file_name: str | None,
        declared_type: str | None,
        stream: BinaryIO,
    ) -> AttachmentOut:
        limit = self._settings.max_upload_bytes
        content = stream.read(limit + 1)
        if len(content) > limit:
            raise file_too_large()
        content_type = normalize_content_type(declared_type)
        if content_type not in self._settings.allowed_content_types:
            raise unsupported_file_type()
        if not content_matches(content_type, content):
            raise unsupported_file_type()
        if self.unlinked_count(actor.id) >= self._settings.max_files_per_ticket:
            raise validation_error(
                {FILE_FIELD: "Remove an unused upload before adding another file"}
            )
        key = self._storage.save(io.BytesIO(content), STORAGE_HINT)
        attachment = Attachment(
            uploader_id=actor.id,
            file_name=sanitize_file_name(file_name),
            content_type=content_type,
            size_bytes=len(content),
            storage_key=key,
            sha256=hashlib.sha256(content).hexdigest(),
            scan_status=self._scanner.scan(content),
            created_at=self._clock.now(),
        )
        self._session.add(attachment)
        self._session.flush()
        return attachment_out(attachment)

    def unlinked_count(self, user_id: uuid.UUID) -> int:
        statement = select(func.count()).where(
            Attachment.uploader_id == user_id, Attachment.ticket_id.is_(None)
        )
        return self._session.scalar(statement) or 0

    def download(self, actor: Actor, attachment_id: str) -> Download:
        attachment = self._downloadable(actor, attachment_id)
        if attachment.ticket_id is not None:
            ticket = self._session.get(Ticket, attachment.ticket_id)
            if ticket is not None and ticket.confidential:
                self._audit.record(
                    action="attachment_downloaded",
                    object_type="attachment",
                    object_id=attachment.id,
                    actor_id=actor.id,
                    ticket_id=ticket.id,
                    department_id=ticket.department_id,
                    is_confidential_ticket=True,
                )
        return Download(attachment=attachment, stream=self._storage.open(attachment.storage_key))

    def _downloadable(self, actor: Actor, attachment_id: str) -> Attachment:
        try:
            parsed = uuid.UUID(attachment_id)
        except ValueError as exc:
            raise not_found() from exc
        attachment = self._session.get(Attachment, parsed)
        if attachment is None or attachment.scan_status is not ScanStatus.CLEAN:
            raise not_found()
        if attachment.ticket_id is None:
            if attachment.uploader_id != actor.id:
                raise not_found()
            return attachment
        ticket = self._session.get(Ticket, attachment.ticket_id)
        if ticket is None or not can_view_ticket(self._session, actor, ticket):
            raise not_found()
        return attachment
