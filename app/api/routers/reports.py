from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.core.enums import Priority
from app.schemas.reports import KpiReportOut
from app.services.kpis import KpiQuery, KpiService

router = APIRouter(tags=["reports"])


@router.get("/reports/kpis", response_model=KpiReportOut)
def kpi_report(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    department_id: Annotated[str | None, Query(max_length=6)] = None,
    priority: Annotated[list[Priority] | None, Query()] = None,
    priority_list: Annotated[list[Priority] | None, Query(alias="priority[]")] = None,
) -> KpiReportOut:
    query = KpiQuery(
        start=start,
        end=end,
        department_id=department_id,
        priorities=[*(priority or []), *(priority_list or [])],
    )
    return KpiService(db, clock).report(actor, query)
