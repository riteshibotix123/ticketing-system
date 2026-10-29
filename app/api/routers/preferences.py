from fastapi import APIRouter

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.preferences import NotificationPreferencesBody, NotificationPreferencesOut
from app.services.preferences import PreferenceService

router = APIRouter(tags=["notifications"])


@router.get("/me/notification-preferences", response_model=NotificationPreferencesOut)
def read_preferences(
    actor: CurrentActor, db: DbSession, clock: ClockDep
) -> NotificationPreferencesOut:
    return PreferenceService(db, clock).read(actor)


@router.put("/me/notification-preferences", response_model=NotificationPreferencesOut)
def replace_preferences(
    body: NotificationPreferencesBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> NotificationPreferencesOut:
    return PreferenceService(db, clock).replace(actor, body)
