from fastapi import APIRouter

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.dashboards import AdminDashboardOut, EmployeeDashboardOut, SpokeDashboardOut
from app.services.dashboards import DashboardService

router = APIRouter(tags=["dashboards"])


@router.get("/dashboard/employee", response_model=EmployeeDashboardOut)
def employee_dashboard(actor: CurrentActor, db: DbSession, clock: ClockDep) -> EmployeeDashboardOut:
    return DashboardService(db, clock).employee(actor)


@router.get("/dashboard/spoke", response_model=SpokeDashboardOut)
def spoke_dashboard(actor: CurrentActor, db: DbSession, clock: ClockDep) -> SpokeDashboardOut:
    return DashboardService(db, clock).spoke(actor)


@router.get("/dashboard/admin", response_model=AdminDashboardOut)
def admin_dashboard(actor: CurrentActor, db: DbSession, clock: ClockDep) -> AdminDashboardOut:
    return DashboardService(db, clock).admin(actor)
