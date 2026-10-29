from fastapi import APIRouter

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.org import (
    AddSpokeBody,
    CreateDepartmentBody,
    DepartmentOut,
    EscalationContactBody,
    UpdateDepartmentBody,
)
from app.services.departments import DepartmentService

router = APIRouter(tags=["departments"])


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(actor: CurrentActor, db: DbSession, clock: ClockDep) -> list[DepartmentOut]:
    return DepartmentService(db, clock).list_departments(actor)


@router.post("/departments", response_model=DepartmentOut)
def create_department(
    body: CreateDepartmentBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DepartmentOut:
    return DepartmentService(db, clock).create(actor, body.id, body.name)


@router.patch("/departments/{id}", response_model=DepartmentOut)
def update_department(
    id: str, body: UpdateDepartmentBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DepartmentOut:
    return DepartmentService(db, clock).update(
        actor, id, body.name, body.active, body.sla_mode_change()
    )


@router.post("/departments/{id}/spokes", response_model=DepartmentOut)
def add_spoke(
    id: str, body: AddSpokeBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DepartmentOut:
    return DepartmentService(db, clock).add_spoke(actor, id, body.user_id)


@router.delete("/departments/{id}/spokes/{user_id}", response_model=DepartmentOut)
def remove_spoke(
    id: str, user_id: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DepartmentOut:
    return DepartmentService(db, clock).remove_spoke(actor, id, user_id)


@router.put("/departments/{id}/escalation", response_model=DepartmentOut)
def set_escalation_contact(
    id: str, body: EscalationContactBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DepartmentOut:
    return DepartmentService(db, clock).set_escalation_contact(actor, id, body.contact_id)
