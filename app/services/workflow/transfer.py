import uuid
from typing import Final

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import AccountState, TicketAction, TicketStatus
from app.core.errors import validation_error
from app.core.events import TicketTransferred
from app.models.identity import User
from app.models.org import Category, Department
from app.policy import Actor
from app.schemas.tickets import TicketOut
from app.schemas.workflow import TransferBody
from app.services.spokes import active_spoke_of
from app.services.workflow.common import AuditEntry, TimelineEntry, Workflow, event_data

DEPARTMENT_FIELD: Final = "department_id"
CATEGORY_FIELD: Final = "category_id"


class TransferService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._flow = Workflow(session, clock)

    def transfer(self, actor: Actor, ticket_no: str, body: TransferBody) -> TicketOut:
        ticket, _ctx, now = self._flow.begin(actor, ticket_no, TicketAction.TRANSFER)
        if body.department_id == ticket.department_id:
            raise validation_error({DEPARTMENT_FIELD: "Choose a different department"})
        department = self._accepting_department(body.department_id)
        category = self._category(department, body.category_id)
        old = {
            "department_id": ticket.department_id,
            "category_id": ticket.category_id,
            "status": ticket.status,
            "owner_id": ticket.owner_id,
            "assignee_id": ticket.assignee_id,
            "confidential": ticket.confidential,
        }
        from_department = ticket.department_id
        ticket.department_id = department.id
        ticket.category_id = category.id if category else None
        ticket.confidential = ticket.confidential or bool(category and category.is_confidential)
        ticket.status = TicketStatus.NEW
        ticket.owner_id = None
        ticket.assignee_id = None
        ticket.eta = None
        ticket.next_checkpoint_at = None
        ticket.hold_reason = None
        ticket.hold_review_date = None
        ticket.awaiting_since = None
        ticket.sla_started_at = now
        change = f"Transferred from {from_department} to {department.id}"
        self._flow.record(
            ticket,
            actor.id,
            now,
            TimelineEntry(
                action="transferred",
                detail=f"{change}. Reason: {body.reason}",
                public_detail=change,
                public=True,
                data=event_data(from_department=from_department, to_department=department.id),
            ),
            AuditEntry(
                action="ticket_transferred",
                old_value=old,
                new_value={
                    "department_id": ticket.department_id,
                    "category_id": ticket.category_id,
                    "status": ticket.status,
                    "confidential": ticket.confidential,
                },
                reason=body.reason,
            ),
        )
        self._flow.publish(
            TicketTransferred(
                actor_id=actor.id,
                occurred_at=now,
                ticket_id=ticket.id,
                from_department=from_department,
                to_department=department.id,
            )
        )
        return self._flow.respond(actor, ticket)

    def _accepting_department(self, department_id: str) -> Department:
        department = self._session.get(Department, department_id)
        has_spoke = select(
            exists().where(User.state == AccountState.ACTIVE, active_spoke_of(department_id))
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
