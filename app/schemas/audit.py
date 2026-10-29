from datetime import datetime

from pydantic import Field

from app.core.types import JsonValue
from app.schemas.common import ApiModel, SystemActor, UserRef, is_none


class AuditEntryOut(ApiModel):
    id: str
    at: datetime
    actor: UserRef | SystemActor
    action: str
    object_type: str
    object_id: str | None
    old_value: JsonValue = Field(default=None, exclude_if=is_none)
    new_value: JsonValue = Field(default=None, exclude_if=is_none)
    reason: str | None = Field(default=None, exclude_if=is_none)
    detail: str | None = Field(default=None, exclude_if=is_none)
