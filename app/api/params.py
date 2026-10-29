from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query
from pydantic import AwareDatetime

from app.core.clock import assume_utc
from app.core.enums import Priority
from app.schemas.tickets import SlaStateFilter, TicketScope
from app.services.ticket_reads import TicketListQuery

QUERY_MAX_LENGTH = 200
ID_MAX_LENGTH = 64


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
        created_from=assume_utc(created_from),
        created_to=assume_utc(created_to),
        sort=sort,
    )


TicketListParams = Annotated[TicketListQuery, Depends(ticket_list_query)]
