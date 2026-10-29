from fastapi import APIRouter, Response, status

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.saved_views import SavedViewCreate, SavedViewOut, SavedViewUpdate
from app.services.saved_views import SavedViewService

router = APIRouter(tags=["saved-views"])


@router.get("/saved-views", response_model=list[SavedViewOut])
def list_saved_views(actor: CurrentActor, db: DbSession, clock: ClockDep) -> list[SavedViewOut]:
    return SavedViewService(db, clock).list_views(actor)


@router.post("/saved-views", response_model=SavedViewOut, status_code=status.HTTP_201_CREATED)
def create_saved_view(
    body: SavedViewCreate, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> SavedViewOut:
    return SavedViewService(db, clock).create(actor, body)


@router.patch("/saved-views/{id}", response_model=SavedViewOut)
def update_saved_view(
    id: str, body: SavedViewUpdate, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> SavedViewOut:
    return SavedViewService(db, clock).update(actor, id, body)


@router.delete("/saved-views/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(id: str, actor: CurrentActor, db: DbSession, clock: ClockDep) -> Response:
    SavedViewService(db, clock).delete(actor, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
