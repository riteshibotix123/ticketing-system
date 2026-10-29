import uuid
from collections.abc import Sequence
from typing import Final

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.enums import AccountState, ScanStatus, TicketStatus
from app.core.errors import validation_error
from app.core.events import TicketCreated, publish
from app.models.identity import User
from app.models.org import Category, Department, SpokeAssignment
from app.models.ticket import Attachment, Ticket, TicketEvent, TicketEventKind
from app.policy import Actor
from app.schemas.tickets import CreateTicketBody, TicketOut
from app.services.audit import AuditService
from app.services.ticket_numbers import TicketNumberService
from app.services.ticket_reads import TicketPresenter

DEPARTMENT_FIELD: Final = "department_id"
CATEGORY_FIELD: Final = "category_id"
ATTACHMENTS_FIELD: Final = "attachment_ids"
CREATED_ACTION: Final = "created"


class TicketService:
    def __init__(self, session: Session, clock: Clock, settings: Settings) -> None:
        self._session = session
        self._clock = clock
        self._settings = settings
        self._audit = AuditService(session, clock)
        self._numbers = TicketNumberService(session)
        self._presenter = TicketPresenter(session, clock)

    def create(self, actor: Actor, body: CreateTicketBody) -> TicketOut:
        department = self._accepting_department(body.department_id)
        category = self._category(department, body.category_id)
        attachments = self._attachments(actor, body.attachment_ids)
        now = self._clock.now()
        confidential = body.confidential or bool(category and category.is_confidential)
        ticket = Ticket(
            ticket_no=self._numbers.next_number(department.id, now),
            origin_department_code=department.id,
            department_id=department.id,
            category_id=category.id if category else None,
            title=body.title,
            description=body.description,
            requested_priority=body.priority,
            priority=body.priority,
            confidential=confidential,
            status=TicketStatus.NEW,
            requester_id=actor.id,
            sla_started_at=now,
            reopen_count=0,
            escalation_level=0,
            update_overdue=False,
            created_at=now,
            updated_at=now,
        )
        self._session.add(ticket)
        self._session.flush()
        for attachment in attachments:
            attachment.ticket_id = ticket.id
        self._session.add(
            TicketEvent(
                ticket_id=ticket.id,
                at=now,
                actor_id=actor.id,
                kind=TicketEventKind.AUDIT,
                action=CREATED_ACTION,
                is_public=True,
            )
        )
        self._audit.record(
            action="ticket_created",
            object_type="ticket",
            object_id=ticket.ticket_no,
            actor_id=actor.id,
            new_value={
                "status": ticket.status,
                "priority": ticket.priority,
                "department_id": department.id,
                "category_id": ticket.category_id,
                "confidential": confidential,
                "attachments": len(attachments),
            },
            ticket_id=ticket.id,
            department_id=department.id,
            is_confidential_ticket=confidential,
        )
        self._session.flush()
        publish(
            self._session, TicketCreated(actor_id=actor.id, occurred_at=now, ticket_id=ticket.id)
        )
        return self._presenter.present_one(actor, ticket)

    def _accepting_department(self, department_id: str) -> Department:
        department = self._session.get(Department, department_id)
        has_spoke = select(
            exists().where(
                SpokeAssignment.department_id == department_id,
                SpokeAssignment.revoked_at.is_(None),
                SpokeAssignment.user_id == User.id,
                User.state == AccountState.ACTIVE,
            )
        )
        if department is None or not department.is_active or not self._session.scalar(has_spoke):
            raise validation_error({DEPARTMENT_FIELD: "This department is not accepting tickets"})
        return department

    def _category(self, department: Department, category_id: str | None) -> Category | None:
        if category_id is None:
            has_active = select(
                exists().where(
                    Category.department_id == department.id, Category.is_active.is_(True)
                )
            )
            if self._session.scalar(has_active):
                raise validation_error({CATEGORY_FIELD: "Choose a category"})
            return None
        try:
            parsed = uuid.UUID(category_id)
        except ValueError as exc:
            raise validation_error({CATEGORY_FIELD: "Choose a category"}) from exc
        category = self._session.get(Category, parsed)
        if category is None or category.department_id != department.id or not category.is_active:
            raise validation_error({CATEGORY_FIELD: "Choose an active category of this department"})
        return category

    def _attachments(self, actor: Actor, attachment_ids: Sequence[str]) -> list[Attachment]:
        if not attachment_ids:
            return []
        invalid = validation_error({ATTACHMENTS_FIELD: "Attach only your own unused uploads"})
        unique_ids = list(dict.fromkeys(attachment_ids))
        if len(unique_ids) != len(attachment_ids):
            raise invalid
        if len(unique_ids) > self._settings.max_files_per_ticket:
            raise validation_error(
                {ATTACHMENTS_FIELD: (f"Attach at most {self._settings.max_files_per_ticket} files")}
            )
        try:
            parsed = sorted(uuid.UUID(value) for value in unique_ids)
        except ValueError as exc:
            raise invalid from exc
        statement = (
            select(Attachment)
            .where(Attachment.id.in_(parsed))
            .order_by(Attachment.id)
            .with_for_update()
        )
        attachments = list(self._session.scalars(statement))
        if len(attachments) != len(parsed) or any(
            attachment.uploader_id != actor.id
            or attachment.ticket_id is not None
            or attachment.scan_status is ScanStatus.INFECTED
            for attachment in attachments
        ):
            raise invalid
        return attachments
