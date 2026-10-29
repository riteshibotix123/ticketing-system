from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from app.models.preferences import NonCriticalEmail
from app.schemas.common import ApiModel

DigestHour = Annotated[int, Field(strict=True, ge=0, le=23)]


class NotificationPreferencesOut(ApiModel):
    non_critical_email: NonCriticalEmail
    digest_hour: int
    critical_email: Literal["always"]


class NotificationPreferencesBody(ApiModel):
    model_config = ConfigDict(extra="forbid")

    non_critical_email: NonCriticalEmail
    digest_hour: DigestHour
