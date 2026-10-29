from fastapi import APIRouter, Response, status

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.calendar import BusinessCalendarOut, CalendarBody, HolidayBody
from app.services.calendar import CalendarService

router = APIRouter(tags=["calendar"])


@router.get("/calendar", response_model=BusinessCalendarOut)
def read_calendar(actor: CurrentActor, db: DbSession, clock: ClockDep) -> BusinessCalendarOut:
    return CalendarService(db, clock).read(actor)


@router.put("/calendar", response_model=BusinessCalendarOut)
def update_calendar(
    body: CalendarBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> BusinessCalendarOut:
    return CalendarService(db, clock).update(actor, body)


@router.post(
    "/calendar/holidays",
    response_model=BusinessCalendarOut,
    status_code=status.HTTP_201_CREATED,
)
def add_holiday(
    body: HolidayBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> BusinessCalendarOut:
    return CalendarService(db, clock).add_holiday(actor, body)


@router.delete("/calendar/holidays/{date}", status_code=status.HTTP_204_NO_CONTENT)
def remove_holiday(date: str, actor: CurrentActor, db: DbSession, clock: ClockDep) -> Response:
    CalendarService(db, clock).remove_holiday(actor, date)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
