from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints

from app.core.enums import Priority, ScanStatus, TicketAction, TicketStatus
from app.models.ticket import TicketEventKind
from app.schemas.common import ApiModel, SystemActor, UserRef
from app.services.sla.sla_object import SlaState


class TicketScope(StrEnum):
    MINE = "mine"
    ASSIGNED = "assigned"
    QUEUE = "queue"
    ALL = "all"


class SlaStateFilter(StrEnum):
    UNACKNOWLEDGED = "unacknowledged"
    WARNING = "warning"
    BREACHED = "breached"
    STALE = "stale"


OPEN_STATUS = "open"


class AttachmentOut(ApiModel):
    id: str
    name: str
    size: int
    mime: str
    scan_status: ScanStatus


class HoldOut(ApiModel):
    reason: str
    review_date: datetime


class FeedbackOut(ApiModel):
    rating: int | None
    comment: str | None


class TicketOut(ApiModel):
    id: str
    title: str
    description: str
    department_id: str
    category_id: str | None
    category_name: str | None
    priority: Priority
    requested_priority: Priority
    status: TicketStatus
    confidential: bool
    requester: UserRef
    owner: UserRef | None
    assignee: UserRef | None
    collaborators: list[UserRef]
    created_at: datetime
    sla_started_at: datetime
    acknowledged_at: datetime | None
    eta: datetime | None
    next_checkpoint_at: datetime | None
    last_team_update_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    reopen_count: int
    hold: HoldOut | None
    resolution_summary: str | None
    feedback: FeedbackOut | None
    sla: SlaState
    allowed_actions: list[TicketAction]
    attachments: list[AttachmentOut]


class TimelineEventOut(ApiModel):
    id: str
    at: datetime
    actor: UserRef | SystemActor
    type: TicketEventKind
    action: str | None = None
    detail: str | None = None
    body: str | None = None
    public: bool


TicketTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TicketDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
EntityId = Annotated[str, Field(min_length=1, max_length=64)]


class CreateTicketBody(ApiModel):
    department_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=6)]
    category_id: EntityId | None = None
    title: TicketTitle
    description: TicketDescription
    priority: Priority
    confidential: bool = False
    attachment_ids: list[EntityId] = []


CommentText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class CommentBody(ApiModel):
    body: CommentText
    internal: bool = False


class CollaboratorBody(ApiModel):
    user_id: EntityId
