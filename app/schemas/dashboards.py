from pydantic import field_serializer

from app.schemas.common import ApiModel
from app.schemas.tickets import TicketOut, TimelineEventOut


class DepartmentHealthOut(ApiModel):
    department_id: str
    name: str
    on_track: int
    warning: int
    breached: int


class EmployeeDashboardOut(ApiModel):
    open: int
    awaiting_my_response: int
    resolved_to_confirm: int
    closed: int
    assigned_to_me: int
    assigned_warning: int
    assigned_breached: int
    recent_updates: list[TimelineEventOut]
    attention: list[TicketOut]

    @field_serializer("recent_updates")
    def _compact_updates(self, value: list[TimelineEventOut]) -> list[dict[str, object]]:
        return [item.model_dump(mode="json", exclude_none=True) for item in value]


class SpokeDashboardOut(ApiModel):
    new_unacknowledged: int
    approaching_sla: int
    breached: int
    stale_or_eta_overdue: int
    awaiting_requester: int
    on_hold: int
    resolved_pending_closure: int
    sla_met_pct: float | None
    avg_initial_response_seconds: int | None
    reopen_rate_pct: float | None
    by_department: list[DepartmentHealthOut]
    attention: list[TicketOut]


class AdminDashboardOut(ApiModel):
    open_count: int
    breached_count: int
    l3_count: int
    stale_count: int
    pending_approvals: int
    sla_met_pct: float | None
    avg_initial_response_seconds: int | None
    reopen_rate_pct: float | None
    by_department: list[DepartmentHealthOut]
    attention: list[TicketOut]
