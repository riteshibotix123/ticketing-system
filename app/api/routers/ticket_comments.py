from fastapi import APIRouter, status

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.tickets import CollaboratorBody, CommentBody, TicketOut, TimelineEventOut
from app.services.collaborators import CollaboratorService
from app.services.comments import CommentService

router = APIRouter(tags=["ticket-comments"])


@router.post(
    "/tickets/{id}/comments",
    response_model=TimelineEventOut,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    id: str, body: CommentBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TimelineEventOut:
    return CommentService(db, clock).add(actor, id, body)


@router.post("/tickets/{id}/collaborators", response_model=TicketOut)
def add_collaborator(
    id: str, body: CollaboratorBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return CollaboratorService(db, clock).add(actor, id, body)


@router.delete("/tickets/{id}/collaborators/{user_id}", response_model=TicketOut)
def remove_collaborator(
    id: str, user_id: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> TicketOut:
    return CollaboratorService(db, clock).remove(actor, id, user_id)
