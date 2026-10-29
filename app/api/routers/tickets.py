from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import ClockDep, CurrentActor, DbSession, SettingsDep
from app.api.params import TicketListParams
from app.core.pagination import PageParams
from app.schemas.common import Page
from app.schemas.tickets import (
    CreateTicketBody,
    TicketOut,
    TimelineEventOut,
)
from app.services.ticket_reads import TicketReadService
from app.services.tickets import TicketService

router = APIRouter(tags=["tickets"])


@router.get("/tickets", response_model=Page[TicketOut])
def list_tickets(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    params: Annotated[PageParams, Depends()],
    query: TicketListParams,
) -> Page[TicketOut]:
    return TicketReadService(db, clock).list_tickets(actor, query, params)


@router.post("/tickets", response_model=TicketOut, status_code=201)
def create_ticket(
    body: CreateTicketBody,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> TicketOut:
    return TicketService(db, clock, settings).create(actor, body)


@router.get("/tickets/{id}", response_model=TicketOut)
def get_ticket(id: str, actor: CurrentActor, db: DbSession, clock: ClockDep) -> TicketOut:
    return TicketReadService(db, clock).get_ticket(actor, id)


@router.get(
    "/tickets/{id}/timeline",
    response_model=list[TimelineEventOut],
    response_model_exclude_none=True,
)
def get_timeline(
    id: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> list[TimelineEventOut]:
    return TicketReadService(db, clock).timeline(actor, id)
