from fastapi import APIRouter, Response, status

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.org import CategoryOut, CreateCategoryBody, UpdateCategoryBody
from app.services.categories import CategoryService

router = APIRouter(tags=["categories"])


@router.post("/departments/{id}/categories", response_model=CategoryOut)
def create_category(
    id: str, body: CreateCategoryBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> CategoryOut:
    return CategoryService(db, clock).create(actor, id, body.name, body.confidential)


@router.patch("/categories/{id}", response_model=CategoryOut)
def update_category(
    id: str, body: UpdateCategoryBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> CategoryOut:
    return CategoryService(db, clock).update(
        actor, id, body.name, body.active, body.confidential, body.sla_mode_change()
    )


@router.delete("/categories/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(id: str, actor: CurrentActor, db: DbSession, clock: ClockDep) -> Response:
    CategoryService(db, clock).deactivate(actor, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
