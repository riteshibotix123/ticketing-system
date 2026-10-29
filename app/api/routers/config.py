from fastapi import APIRouter

from app.api.deps import DbSession, SettingsDep
from app.schemas.auth import PublicConfig
from app.services.policy import PolicyService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/config", response_model=PublicConfig)
def public_config(db: DbSession, settings: SettingsDep) -> PublicConfig:
    return PolicyService(db).public_config(settings)
