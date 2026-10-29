from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.enums import Priority
from app.schemas.common import ApiModel, UserRef

type AgingBucket = Literal["0_2", "3_7", "8_14", "15_30", "31_plus"]


class KpiFiltersOut(ApiModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    department_ids: list[str]
    priorities: list[Priority]


class SlaComplianceOut(ApiModel):
    met: int
    missed: int
    pct: float | None


class DurationOut(ApiModel):
    count: int
    avg_seconds: int | None
    median_seconds: int | None


class TrendPointOut(ApiModel):
    date: str
    count: int
    avg_seconds: int | None


class ReopenOut(ApiModel):
    resolved: int
    reopened: int
    rate_pct: float | None


class EscalationCountsOut(ApiModel):
    l1: int
    l2: int
    l3: int


class AgingOut(ApiModel):
    bucket: AgingBucket
    count: int


class PriorityCountsOut(ApiModel):
    low: int
    medium: int
    high: int
    critical: int


class DepartmentKpiOut(ApiModel):
    department_id: str
    name: str
    active: int
    by_priority: PriorityCountsOut
    on_track: int
    warning: int
    breached: int
    sla_met_pct: float | None


class WorkloadRowOut(ApiModel):
    user: UserRef | None
    active: int
    breached: int


class WorkloadOut(ApiModel):
    by_assignee: list[WorkloadRowOut]
    by_owner: list[WorkloadRowOut]


class CategoryCountOut(ApiModel):
    category_id: str | None
    name: str
    count: int


class KpiReportOut(ApiModel):
    generated_at: datetime
    filters: KpiFiltersOut
    sla_compliance: SlaComplianceOut
    initial_response: DurationOut
    initial_response_trend: list[TrendPointOut]
    resolution_turnaround: DurationOut
    reopen: ReopenOut
    escalations: EscalationCountsOut
    eta_breach_count: int
    stale_count: int
    overdue_eta_count: int
    unacknowledged_over_24h: int
    persistent_l3_count: int
    aging: list[AgingOut]
    departments: list[DepartmentKpiOut]
    workload: WorkloadOut
    top_categories: list[CategoryCountOut]
