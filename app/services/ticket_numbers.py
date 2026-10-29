from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import to_ist
from app.core.ids import format_ticket_no
from app.models.ticket import TicketCounter


class TicketNumberService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def next_number(self, department_code: str, now: datetime) -> str:
        year = to_ist(now).year
        statement = (
            insert(TicketCounter)
            .values(department_code=department_code, year=year, last_value=1)
            .on_conflict_do_update(
                index_elements=[TicketCounter.department_code, TicketCounter.year],
                set_={"last_value": TicketCounter.last_value + 1},
            )
            .returning(TicketCounter.last_value)
        )
        value = self._session.execute(statement).scalar_one()
        return format_ticket_no(department_code, year, value)
