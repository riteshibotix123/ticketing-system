from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.deps import ClockDep, CurrentActor, DbSession, SettingsDep
from app.core.enums import Priority
from app.core.pagination import PageParams
from app.schemas.common import Page
from app.schemas.tickets import (
    CreateTicketBody,
    SlaStateFilter,
    TicketOut,
    TicketScope,
    TimelineEventOut,
)
from app.services.ticket_reads import TicketListQuery, TicketReadService
from app.services.tickets import TicketService

QUERY_MAX_LENGTH = 200
ID_MAX_LENGTH = 64

router = APIRouter(tags=["tickets"])


def ticket_list_query(
    scope: TicketScope = TicketScope.MINE,
    q: Annotated[str | None, Query(max_length=QUERY_MAX_LENGTH)] = None,
    status: Annotated[list[str] | None, Query(max_length=32)] = None,
    status_list: Annotated[list[str] | None, Query(alias="status[]", max_length=32)] = None,
    priority: Annotated[list[Priority] | None, Query()] = None,
    priority_list: Annotated[list[Priority] | None, Query(alias="priority[]")] = None,
    department_id: Annotated[str | None, Query(max_length=6)] = None,
    category_id: Annotated[str | None, Query(max_length=ID_MAX_LENGTH)] = None,
    sla_state: SlaStateFilter | None = None,
    escalation_level: Annotated[int | None, Query(ge=0, le=3)] = None,
    requester_id: Annotated[str | None, Query(max_length=ID_MAX_LENGTH)] = None,
    assignee_id: Annotated[str | None, Query(max_length=ID_MAX_LENGTH)] = None,
    confidential: bool | None = None,
    overdue_eta: bool = False,
    unassigned: bool = False,
    awaiting_before: AwareDatetime | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: Annotated[str | None, Query(max_length=32)] = None,
) -> TicketListQuery:
    return TicketListQuery(
        scope=scope,
        q=q,
        statuses=[*(status or []), *(status_list or [])],
        priorities=[*(priority or []), *(priority_list or [])],
        department_id=department_id,
        category_id=category_id,
        sla_state=sla_state,
        escalation_level=escalation_level,
        requester_id=requester_id,
        assignee_id=assignee_id,
        confidential=confidential,
        overdue_eta=overdue_eta,
        unassigned=unassigned,
        awaiting_before=awaiting_before,
        created_from=created_from,
        created_to=created_to,
        sort=sort,
    )


TicketListParams = Annotated[TicketListQuery, Depends(ticket_list_query)]


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
