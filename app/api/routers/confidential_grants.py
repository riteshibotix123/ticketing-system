from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.org import ID_MAX_LENGTH, ConfidentialGrantOut, CreateGrantBody
from app.services.confidential_grants import ConfidentialGrantService

router = APIRouter(tags=["confidential-grants"])


@router.get("/confidential-grants", response_model=list[ConfidentialGrantOut])
def list_grants(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    category_id: Annotated[str | None, Query(max_length=ID_MAX_LENGTH)] = None,
    user_id: Annotated[str | None, Query(max_length=ID_MAX_LENGTH)] = None,
) -> list[ConfidentialGrantOut]:
    return ConfidentialGrantService(db, clock).list_grants(actor, category_id, user_id)


@router.post("/confidential-grants", response_model=ConfidentialGrantOut)
def create_grant(
    body: CreateGrantBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ConfidentialGrantOut:
    return ConfidentialGrantService(db, clock).create(actor, body.user_id, body.category_id)


@router.delete("/confidential-grants/{id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_grant(id: str, actor: CurrentActor, db: DbSession, clock: ClockDep) -> Response:
    ConfidentialGrantService(db, clock).revoke(actor, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
