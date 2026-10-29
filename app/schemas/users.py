from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.enums import AccountState, ProtectedActionKind, ProtectedActionStatus, Role
from app.schemas.common import ApiModel, UserRef
from app.schemas.signup import DepartmentCode, Reason

MAX_SPOKE_DEPARTMENTS = 50
ID_MAX_LENGTH = 64


class UserListItem(UserRef):
    roles: list[Role]
    state: AccountState
    department_id: str | None
    spoke_departments: list[str]
    last_login_at: datetime | None
    created_at: datetime


class UpdateRolesBody(ApiModel):
    spoke_departments: list[DepartmentCode] = Field(max_length=MAX_SPOKE_DEPARTMENTS)
    reason: Reason


class DeactivateBody(ApiModel):
    reason: Reason


class DeactivationResult(ApiModel):
    result: Literal["deactivated", "protected_request_created"]
    open_ticket_count: int
    protected_action_id: str | None


class PromoteAdminBody(ApiModel):
    user_id: str = Field(min_length=1, max_length=ID_MAX_LENGTH)


class CreateProtectedActionBody(ApiModel):
    kind: ProtectedActionKind
    target_user_id: str = Field(min_length=1, max_length=ID_MAX_LENGTH)
    reason: Reason


class RejectProtectedActionBody(ApiModel):
    reason: Reason


class ProtectedActionOut(ApiModel):
    id: str
    kind: ProtectedActionKind
    target: UserRef
    requested_by: UserRef
    reason: str
    status: ProtectedActionStatus
    decided_by: UserRef | None = None
    decision_reason: str | None = None
    created_at: datetime
    expires_at: datetime
    can_decide: bool
