from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import Priority
from app.core.security import PASSWORD_MIN_LENGTH
from app.models.org import Department
from app.models.policy import PolicyVersion
from app.schemas.auth import AttachmentLimits, PublicConfig, PublicDepartment


class PolicyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    initial_response_hours: int
    warning_hours: dict[Priority, int]
    l3_hours: dict[Priority, int]
    update_warning_hours: int
    update_cadence_hours: int
    eta_warning_hours: int
    escalation_repeat_hours: int
    requester_reminder_hours: int
    auto_close_business_days: int | None
    reopen_window_days: int
    max_reopens: int
    sla_mode: Literal["calendar", "business"]
    admins_can_manage_departments: bool


class PolicyService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def current_version(self) -> PolicyVersion:
        statement = select(PolicyVersion).order_by(PolicyVersion.version.desc()).limit(1)
        version = self._session.scalars(statement).first()
        if version is None:
            raise LookupError("no policy version exists")
        return version

    def current(self) -> PolicyConfig:
        return PolicyConfig.model_validate(self.current_version().config)

    def public_config(self, settings: Settings) -> PublicConfig:
        departments = self._session.scalars(
            select(Department).where(Department.is_active.is_(True)).order_by(Department.name)
        )
        return PublicConfig(
            allowed_email_domains=list(settings.allowed_email_domains),
            departments=[
                PublicDepartment(id=department.id, name=department.name)
                for department in departments
            ],
            attachment_limits=AttachmentLimits(
                max_bytes=settings.max_upload_bytes,
                max_files=settings.max_files_per_ticket,
                allowed_mime_types=list(settings.allowed_content_types),
            ),
            password_min_length=PASSWORD_MIN_LENGTH,
            first_response_hours=self.current().initial_response_hours,
        )
