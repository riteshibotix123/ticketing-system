from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentActor, DbSession
from app.core.clock import assume_utc
from app.core.pagination import PageParams
from app.schemas.audit import AuditEntryOut
from app.schemas.common import Page
from app.services.audit_reads import AuditReadService

TEXT_MAX_LENGTH = 200
ID_MAX_LENGTH = 64

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=Page[AuditEntryOut])
def list_audit(
    actor: CurrentActor,
    db: DbSession,
    params: Annotated[PageParams, Depends()],
    q: Annotated[str | None, Query(max_length=TEXT_MAX_LENGTH)] = None,
    actor_id: Annotated[str | None, Query(max_length=ID_MAX_LENGTH)] = None,
    action: Annotated[str | None, Query(max_length=ID_MAX_LENGTH)] = None,
    ticket_id: Annotated[str | None, Query(max_length=ID_MAX_LENGTH)] = None,
    created_from: Annotated[datetime | None, Query(alias="from")] = None,
    created_to: Annotated[datetime | None, Query(alias="to")] = None,
) -> Page[AuditEntryOut]:
    return AuditReadService(db).list_entries(
        actor,
        params,
        q=q,
        actor_id=actor_id,
        action=action,
        ticket_id=ticket_id,
        created_from=assume_utc(created_from),
        created_to=assume_utc(created_to),
    )
