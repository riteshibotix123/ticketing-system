from typing import Annotated, Literal

from pydantic import Field

from app.core.enums import Priority
from app.schemas.common import ApiModel

MIN_HOURS = 1
MAX_HOURS = 168
MAX_ETA_WARNING_HOURS = 48
MAX_AUTO_CLOSE_BUSINESS_DAYS = 30
MAX_REOPEN_WINDOW_DAYS = 90
MAX_REOPENS = 10

Hours = Annotated[int, Field(ge=MIN_HOURS, le=MAX_HOURS)]


class PolicyBody(ApiModel):
    initial_response_hours: Hours
    warning_hours: dict[Priority, Hours]
    l3_hours: dict[Priority, Hours]
    update_warning_hours: Hours
    update_cadence_hours: Hours
    eta_warning_hours: Annotated[int, Field(ge=MIN_HOURS, le=MAX_ETA_WARNING_HOURS)]
    escalation_repeat_hours: Hours
    requester_reminder_hours: Hours
    auto_close_business_days: Annotated[int, Field(ge=1, le=MAX_AUTO_CLOSE_BUSINESS_DAYS)] | None
    reopen_window_days: Annotated[int, Field(ge=1, le=MAX_REOPEN_WINDOW_DAYS)]
    max_reopens: Annotated[int, Field(ge=0, le=MAX_REOPENS)]
    sla_mode: Literal["calendar", "business"]
    admins_can_manage_departments: bool
