from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, ConfigDict, Field, StringConstraints

from app.core.enums import Priority
from app.core.types import JsonObject
from app.schemas.common import ApiModel
from app.schemas.tickets import SlaStateFilter, TicketScope

QUERY_TEXT_MAX_LENGTH = 200
ID_MAX_LENGTH = 64

ViewName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class TicketListQueryModel(ApiModel):
    model_config = ConfigDict(extra="forbid")

    scope: TicketScope | None = None
    q: Annotated[str, Field(max_length=QUERY_TEXT_MAX_LENGTH)] | None = None
    status: list[Annotated[str, Field(max_length=32)]] | None = None
    priority: list[Priority] | None = None
    department_id: Annotated[str, Field(max_length=6)] | None = None
    category_id: Annotated[str, Field(max_length=ID_MAX_LENGTH)] | None = None
    sla_state: SlaStateFilter | None = None
    escalation_level: Annotated[int, Field(ge=0, le=3)] | None = None
    requester_id: Annotated[str, Field(max_length=ID_MAX_LENGTH)] | None = None
    assignee_id: Annotated[str, Field(max_length=ID_MAX_LENGTH)] | None = None
    confidential: bool | None = None
    overdue_eta: bool | None = None
    unassigned: bool | None = None
    awaiting_before: AwareDatetime | None = None
    created_from: AwareDatetime | None = None
    created_to: AwareDatetime | None = None
    sort: Annotated[str, Field(max_length=32)] | None = None


class SavedViewCreate(ApiModel):
    name: ViewName
    query: JsonObject


class SavedViewUpdate(ApiModel):
    name: ViewName | None = None
    query: JsonObject | None = None


class SavedViewOut(ApiModel):
    id: str
    name: str
    built_in: bool
    query: JsonObject
    created_at: datetime | None
    updated_at: datetime | None
