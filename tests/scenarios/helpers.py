from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime, timedelta
from typing import Final

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.enums import Role
from app.core.security import create_access_token, hash_password
from app.integrations.email import InMemorySender
from app.models import (
    AuditLog,
    Department,
    EmailOutbox,
    EscalationEvent,
    Notification,
    Ticket,
    User,
)
from app.worker import JobContext
from app.worker.jobs import registered_jobs
from tests.factories import make_department, make_spoke_assignment, make_user

API: Final = "/api/v1"
PASSWORD: Final = "Scenario-Pass-42"
PASSWORD_HASH: Final = hash_password(PASSWORD)
REASON: Final = "Scenario reason text"

type Json = dict[str, object]


@dataclass(frozen=True, slots=True)
class PersonSpec:
    key: str
    name: str
    department: str
    role: Role = Role.EMPLOYEE
    spoke_of: tuple[str, ...] = ()


DEPARTMENTS: Final = {
    "HR": "HR / People Operations",
    "IT": "IT & Infrastructure",
    "ENG": "Engineering",
    "SAL": "Sales",
    "ADM": "Administration",
}
PEOPLE: Final = (
    PersonSpec("asha", "Asha Employee", "ENG"),
    PersonSpec("omar", "Omar Employee", "ENG"),
    PersonSpec("neha", "Neha Spoke", "HR", spoke_of=("HR",)),
    PersonSpec("hari", "Hari Spoke", "HR", spoke_of=("HR",)),
    PersonSpec("hema", "Hema Head", "HR"),
    PersonSpec("harsh", "Harsh Member", "HR"),
    PersonSpec("ira", "Ira Spoke", "IT", spoke_of=("IT",)),
    PersonSpec("ivan", "Ivan Member", "IT"),
    PersonSpec("ishan", "Ishan Head", "IT"),
    PersonSpec("sara", "Sara Spoke", "SAL", spoke_of=("SAL",)),
    PersonSpec("priya", "Priya Admin", "ADM", role=Role.ADMIN),
    PersonSpec("karan", "Karan Super", "ADM", role=Role.SUPER_ADMIN),
    PersonSpec("mira", "Mira Super", "ADM", role=Role.SUPER_ADMIN),
)
CONTACTS: Final = {"HR": "hema", "IT": "ishan"}


@dataclass
class Org:
    departments: dict[str, Department]
    users: dict[str, User]

    def __getitem__(self, key: str) -> User:
        return self.users[key]


def build_org(db: Session) -> Org:
    departments = {code: make_department(db, code, name) for code, name in DEPARTMENTS.items()}
    users: dict[str, User] = {}
    for person in PEOPLE:
        user = make_user(
            db,
            departments[person.department],
            email=f"{person.key}@ibotix.ai",
            name=person.name,
            role=person.role,
            password_hash=PASSWORD_HASH,
        )
        for code in person.spoke_of:
            make_spoke_assignment(db, user, departments[code])
        users[person.key] = user
    for code, key in CONTACTS.items():
        departments[code].escalation_contact_user_id = users[key].id
    db.commit()
    return Org(departments=departments, users=users)


def hours(value: float) -> timedelta:
    return timedelta(hours=value)


@dataclass
class Portal:
    client: TestClient
    db: Session
    clock: FrozenClock
    settings: Settings
    org: Org
    sender: InMemorySender = dataclass_field(default_factory=InMemorySender)

    def headers(self, user: User) -> dict[str, str]:
        token = create_access_token(user.id, self.clock.now(), self.settings).token
        return {"Authorization": f"Bearer {token}"}

    def get(self, who: str, path: str) -> Response:
        response: Response = self.client.get(f"{API}{path}", headers=self.headers(self.org[who]))
        return response

    def post(self, who: str, path: str, body: object = None) -> Response:
        response: Response = self.client.post(
            f"{API}{path}", json=body, headers=self.headers(self.org[who])
        )
        return response

    def delete(self, who: str, path: str) -> Response:
        response: Response = self.client.delete(f"{API}{path}", headers=self.headers(self.org[who]))
        return response

    def anonymous(self, path: str, body: object) -> Response:
        response: Response = self.client.post(f"{API}{path}", json=body)
        return response

    def ok(self, response: Response) -> Json:
        assert response.is_success, response.text
        body = response.json()
        assert isinstance(body, dict)
        return body

    def raise_ticket(
        self,
        who: str,
        department: str,
        *,
        title: str = "Scenario ticket",
        priority: str = "medium",
        category_id: str | None = None,
        confidential: bool = False,
    ) -> str:
        response = self.post(
            who,
            "/tickets",
            {
                "department_id": department,
                "category_id": category_id,
                "title": title,
                "description": f"{title} description",
                "priority": priority,
                "confidential": confidential,
            },
        )
        assert response.status_code == 201, response.text
        number = response.json()["id"]
        assert isinstance(number, str)
        return number

    def acknowledge(self, who: str, number: str, eta_hours: float = 48) -> Json:
        eta = (self.clock.now() + hours(eta_hours)).isoformat()
        return self.ok(self.post(who, f"/tickets/{number}/acknowledge", {"eta": eta}))

    def advance(self, by: timedelta) -> datetime:
        return self.clock.advance(by)

    def set_time(self, at: datetime) -> None:
        self.clock.set(at)

    def run_jobs(self, *names: str) -> dict[str, int]:
        context = JobContext(clock=self.clock, settings=self.settings, sender=self.sender)
        results: dict[str, int] = {}
        for job in registered_jobs():
            if not names or job.name in names:
                results[job.name] = job.run(self.db, context)
        return results

    def scan(self) -> int:
        return self.run_jobs("sla_scan")["sla_scan"]

    def ticket(self, number: str) -> Ticket:
        ticket = self.db.scalars(select(Ticket).where(Ticket.ticket_no == number)).one()
        self.db.refresh(ticket)
        return ticket

    def notified(self, number: str, kind: str, since: datetime | None = None) -> set[str]:
        ticket = self.ticket(number)
        statement = (
            select(User.email)
            .join(Notification, Notification.user_id == User.id)
            .where(Notification.ticket_id == ticket.id, Notification.kind == kind)
        )
        if since is not None:
            statement = statement.where(Notification.created_at >= since)
        return {email.split("@", 1)[0] for email in self.db.scalars(statement)}

    def notification_count(self, number: str, kind: str) -> int:
        ticket = self.ticket(number)
        return len(
            self.db.scalars(
                select(Notification.id).where(
                    Notification.ticket_id == ticket.id, Notification.kind == kind
                )
            ).all()
        )

    def steps(self, number: str) -> list[tuple[str, str, int]]:
        ticket = self.ticket(number)
        rows = self.db.execute(
            select(EscalationEvent.timer_kind, EscalationEvent.step_key, EscalationEvent.cycle)
            .where(EscalationEvent.ticket_id == ticket.id)
            .order_by(EscalationEvent.at, EscalationEvent.step_key)
        ).tuples()
        return [(str(kind.value), key, cycle) for kind, key, cycle in rows]

    def step_keys(self, number: str, timer: str) -> set[str]:
        return {key for kind, key, _ in self.steps(number) if kind == timer}

    def audit_actions(self) -> list[str]:
        return list(self.db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)))

    def emails_to(self, who: str) -> list[EmailOutbox]:
        address = self.org[who].email
        return list(self.db.scalars(select(EmailOutbox).where(EmailOutbox.to_address == address)))


def error_code(response: Response) -> str:
    body = response.json()
    assert isinstance(body, dict)
    error = body["error"]
    assert isinstance(error, dict)
    code = error["code"]
    assert isinstance(code, str)
    return code


def item_ids(page: Json) -> list[str]:
    items = page["items"]
    assert isinstance(items, list)
    return [str(item["id"]) for item in items]


def field(body: Json, *path: str) -> object:
    value: object = body
    for key in path:
        assert isinstance(value, dict), path
        value = value[key]
    return value
