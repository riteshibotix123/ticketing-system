from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.models.calendar import SlaMode
from app.schemas.common import ApiModel, UserRef

ID_MAX_LENGTH = 64

DepartmentId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z]{2,6}$")]
OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
EntityId = Annotated[str, Field(min_length=1, max_length=ID_MAX_LENGTH)]


class CategoryOut(ApiModel):
    id: str
    department_id: str
    name: str
    confidential: bool
    active: bool
    sla_mode: SlaMode | None


class DepartmentOut(ApiModel):
    id: str
    name: str
    active: bool
    accepts_tickets: bool
    spokes: list[UserRef]
    escalation_contact: UserRef | None
    categories: list[CategoryOut]
    sla_mode: SlaMode | None


@dataclass(frozen=True, slots=True)
class SlaModeChange:
    sla_mode: SlaMode | None


class SlaModeField(ApiModel):
    sla_mode: SlaMode | None = None

    def sla_mode_change(self) -> SlaModeChange | None:
        if "sla_mode" not in self.model_fields_set:
            return None
        return SlaModeChange(self.sla_mode)


class CreateDepartmentBody(ApiModel):
    id: DepartmentId
    name: OrgName


class UpdateDepartmentBody(SlaModeField):
    name: OrgName | None = None
    active: bool | None = None


class AddSpokeBody(ApiModel):
    user_id: EntityId


class EscalationContactBody(ApiModel):
    contact_id: EntityId | None


class CreateCategoryBody(ApiModel):
    name: OrgName
    confidential: bool = False


class UpdateCategoryBody(SlaModeField):
    name: OrgName | None = None
    active: bool | None = None
    confidential: bool | None = None


class CreateGrantBody(ApiModel):
    user_id: EntityId
    category_id: EntityId


class ConfidentialGrantOut(ApiModel):
    id: str
    user: UserRef
    category: CategoryOut
    granted_by: UserRef | None
    granted_at: datetime
