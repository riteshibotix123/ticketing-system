from datetime import timedelta
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import ClockDep, SettingsDep
from app.core.db import get_db
from app.models.notification import WorkerHeartbeat
from app.worker.main import HEARTBEAT_NAME

STALE_AFTER_TICKS: Final = 3

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok"]


@router.get("/live")
def live() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/ready")
def ready(db: Annotated[Session, Depends(get_db, scope="function")]) -> HealthStatus:
    db.execute(text("SELECT 1"))
    return HealthStatus(status="ok")


@router.get("/worker", response_model=HealthStatus)
def worker(
    db: Annotated[Session, Depends(get_db, scope="function")],
    clock: ClockDep,
    settings: SettingsDep,
) -> HealthStatus | JSONResponse:
    heartbeat = db.get(WorkerHeartbeat, HEARTBEAT_NAME)
    limit = timedelta(seconds=settings.worker_tick_seconds * STALE_AFTER_TICKS)
    if heartbeat is None or clock.now() - heartbeat.last_seen_at > limit:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "stale"}
        )
    return HealthStatus(status="ok")
