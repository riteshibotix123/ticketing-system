from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from app.core.enums import AccountState, Role, SignupStatus
from app.schemas.auth import NormalizedEmail
from app.schemas.common import ApiModel, UserRef

SIGNUP_ROLES = frozenset({Role.EMPLOYEE, Role.ADMIN, Role.SUPER_ADMIN})


def ensure_signup_role(value: Role) -> Role:
    if value not in SIGNUP_ROLES:
        raise ValueError("Must be one of: employee, admin, super_admin")
    return value


SignupRole = Annotated[Role, AfterValidator(ensure_signup_role)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
DepartmentCode = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6)
]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=1000)]


class SignupBody(ApiModel):
    name: PersonName
    email: NormalizedEmail
    password: str = Field(max_length=1024)
    requested_role: SignupRole
    requested_department: DepartmentCode


class SignupAccepted(ApiModel):
    message: str


class VerifyEmailBody(ApiModel):
    token: str = Field(min_length=1, max_length=512)


class VerifyEmailResult(ApiModel):
    state: AccountState


class ResendVerificationBody(ApiModel):
    email: NormalizedEmail


class ReapplyBody(ApiModel):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=1024)
    requested_role: SignupRole
    requested_department: DepartmentCode


class ApproveSignupBody(ApiModel):
    approved_role: SignupRole
    approved_department: DepartmentCode


class RejectSignupBody(ApiModel):
    reason: Reason


class SignupRequestOut(ApiModel):
    id: str
    name: str
    email: str
    email_verified: bool
    requested_role: Role
    requested_department: str
    approved_role: Role | None = None
    approved_department: str | None = None
    status: SignupStatus
    decided_by: UserRef | None = None
    decided_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    can_approve: bool
