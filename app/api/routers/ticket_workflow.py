from fastapi import APIRouter

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.tickets import TicketOut
from app.schemas.workflow import (
    AcknowledgeBody,
    AssignBody,
    ConfirmClosureBody,
    EtaBody,
    HoldBody,
    PriorityBody,
    ReasonBody,
    ResolveBody,
    StatusBody,
    TransferBody,
)
from app.services.workflow.closure import ClosureService
from app.services.workflow.progress import ProgressService
from app.services.workflow.transfer import TransferService

router = APIRouter(tags=["ticket-workflow"])


@router.post("/tickets/{id}/acknowledge", response_model=TicketOut)
def acknowledge(
    id: str, body: AcknowledgeBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ProgressService(db, clock).acknowledge(actor, id, body)


@router.post("/tickets/{id}/assign", response_model=TicketOut)
def assign(
    id: str, body: AssignBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ProgressService(db, clock).assign(actor, id, body)


@router.post("/tickets/{id}/status", response_model=TicketOut)
def change_status(
    id: str, body: StatusBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ProgressService(db, clock).change_status(actor, id, body)


@router.post("/tickets/{id}/hold", response_model=TicketOut)
def hold(id: str, body: HoldBody, actor: CurrentActor, db: DbSession, clock: ClockDep) -> TicketOut:
    return ProgressService(db, clock).hold(actor, id, body)


@router.post("/tickets/{id}/eta", response_model=TicketOut)
def revise_eta(
    id: str, body: EtaBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ProgressService(db, clock).revise_eta(actor, id, body)


@router.post("/tickets/{id}/priority", response_model=TicketOut)
def change_priority(
    id: str, body: PriorityBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ProgressService(db, clock).change_priority(actor, id, body)


@router.post("/tickets/{id}/resolve", response_model=TicketOut)
def resolve(
    id: str, body: ResolveBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ClosureService(db, clock).resolve(actor, id, body)


@router.post("/tickets/{id}/confirm-closure", response_model=TicketOut)
def confirm_closure(
    id: str, body: ConfirmClosureBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ClosureService(db, clock).confirm_closure(actor, id, body)


@router.post("/tickets/{id}/reopen", response_model=TicketOut)
def reopen(
    id: str, body: ReasonBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ClosureService(db, clock).reopen(actor, id, body)


@router.post("/tickets/{id}/cancel", response_model=TicketOut)
def cancel(
    id: str, body: ReasonBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ClosureService(db, clock).cancel(actor, id, body)


@router.post("/tickets/{id}/close", response_model=TicketOut)
def close(
    id: str, body: ReasonBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return ClosureService(db, clock).close(actor, id, body)


@router.post("/tickets/{id}/transfer", response_model=TicketOut)
def transfer(
    id: str, body: TransferBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return TransferService(db, clock).transfer(actor, id, body)
