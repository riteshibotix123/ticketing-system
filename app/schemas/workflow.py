from typing import Annotated

from pydantic import AwareDatetime, Field, StringConstraints

from app.core.enums import Priority, TicketStatus
from app.schemas.common import ApiModel
from app.schemas.signup import Reason
from app.schemas.tickets import EntityId

StatusMessage = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=5, max_length=5000)
]


class AcknowledgeBody(ApiModel):
    eta: AwareDatetime | None = None
    no_eta_reason: Reason | None = None
    next_checkpoint_at: AwareDatetime | None = None


class AssignBody(ApiModel):
    assignee_id: EntityId
    reason: Reason | None = None


class StatusBody(ApiModel):
    status: TicketStatus
    message: StatusMessage | None = None


class HoldBody(ApiModel):
    reason: Reason
    review_date: AwareDatetime


class EtaBody(ApiModel):
    eta: AwareDatetime
    reason: Reason


class PriorityBody(ApiModel):
    priority: Priority
    reason: Reason


ResolutionSummary = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)
]
FeedbackComment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class ResolveBody(ApiModel):
    summary: ResolutionSummary


class ConfirmClosureBody(ApiModel):
    rating: Annotated[int, Field(ge=1, le=5)] | None = None
    comment: FeedbackComment | None = None


class ReasonBody(ApiModel):
    reason: Reason


class TransferBody(ApiModel):
    department_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=6)]
    category_id: EntityId | None = None
    reason: Reason
