from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, Field

from app.core.enums import Role
from app.models.identity import Theme
from app.schemas.common import ApiModel, UserRef, is_none

EMAIL_MAX_LENGTH = 320


def normalize_email(value: str) -> str:
    candidate = value.strip().lower()
    try:
        validate_email(candidate, check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError("Enter a valid email address") from exc
    return candidate


NormalizedEmail = Annotated[
    str, Field(min_length=3, max_length=EMAIL_MAX_LENGTH), AfterValidator(normalize_email)
]


class Me(UserRef):
    roles: list[Role]
    department_id: str | None
    spoke_departments: list[str]
    permissions: list[str]
    mfa_enabled: bool
    theme: Theme | None = Field(default=None, exclude_if=is_none)


class LoginRequest(ApiModel):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=1024)


class LoginSuccess(ApiModel):
    access_token: str
    expires_in: int
    user: Me


class MfaRequired(ApiModel):
    mfa_required: Literal[True] = True
    mfa_token: str


class MfaEnrolRequired(ApiModel):
    mfa_enrol_required: Literal[True] = True
    mfa_token: str


class MfaTokenRequest(ApiModel):
    mfa_token: str = Field(min_length=1, max_length=2048)


class MfaCodeRequest(MfaTokenRequest):
    code: str = Field(min_length=1, max_length=64)


class MfaSetupResponse(ApiModel):
    secret: str
    otpauth_uri: str


class MfaConfirmSuccess(LoginSuccess):
    recovery_codes: list[str]


class RefreshResponse(ApiModel):
    access_token: str
    expires_in: int


class ForgotPasswordRequest(ApiModel):
    email: NormalizedEmail


class ResetPasswordRequest(ApiModel):
    token: str = Field(min_length=1, max_length=512)
    password: str = Field(max_length=1024)


class PublicDepartment(ApiModel):
    id: str
    name: str


class AttachmentLimits(ApiModel):
    max_bytes: int
    max_files: int
    allowed_mime_types: list[str]


class PublicConfig(ApiModel):
    allowed_email_domains: list[str]
    departments: list[PublicDepartment]
    attachment_limits: AttachmentLimits
    password_min_length: int
    first_response_hours: int
