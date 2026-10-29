from fastapi import APIRouter

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.policy import PolicyBody
from app.services.policy import PolicyConfig
from app.services.policy_admin import PolicyAdminService

router = APIRouter(tags=["policy"])


@router.get("/policy", response_model=PolicyConfig)
def read_policy(actor: CurrentActor, db: DbSession, clock: ClockDep) -> PolicyConfig:
    return PolicyAdminService(db, clock).read(actor)


@router.put("/policy", response_model=PolicyConfig)
def replace_policy(
    body: PolicyBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> PolicyConfig:
    return PolicyAdminService(db, clock).replace(actor, body)
