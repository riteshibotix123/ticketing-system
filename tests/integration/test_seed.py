import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.enums import AccountState, TicketStatus
from app.core.security import create_access_token
from app.models import (
    AuditLog,
    Category,
    ConfidentialGrant,
    Department,
    EscalationEvent,
    Notification,
    RateLimitHit,
    SignupRequest,
    SpokeAssignment,
    Ticket,
    User,
)
from app.seed.data import PEOPLE, SEED_PASSWORD, email_for
from app.seed.run import SeedRefused, SeedResult, seed

LOGIN = "/api/v1/auth/login"


@pytest.fixture
def seeded(db: Session, settings: Settings, clock: FrozenClock) -> SeedResult:
    result = seed(db, settings, clock)
    db.commit()
    return result


def count(db: Session, model: type[object]) -> int:
    value = db.scalar(select(func.count()).select_from(model))
    assert isinstance(value, int)
    return value


def user_by_name(db: Session, name: str) -> User:
    user = db.scalars(select(User).where(User.email == email_for(name))).one()
    return user


def ticket_titled(db: Session, title: str) -> Ticket:
    return db.scalars(select(Ticket).where(Ticket.title == title)).one()


def test_seed_builds_departments_people_and_categories(db: Session, seeded: SeedResult) -> None:
    assert seeded.created
    assert seeded.users == len(PEOPLE)
    departments = {department.id: department for department in db.scalars(select(Department))}
    assert set(departments) == {"IT", "ENG", "HR", "ADM", "FIN", "SEC", "SAL", "OPS", "LEG"}
    assert departments["SAL"].escalation_contact_user_id is None
    assert all(
        department.escalation_contact_user_id is not None
        for code, department in departments.items()
        if code != "SAL"
    )
    spoke_departments = set(db.scalars(select(SpokeAssignment.department_id)))
    assert spoke_departments == set(departments) - {"ADM"}
    per_department = db.execute(
        select(Category.department_id, func.count()).group_by(Category.department_id)
    ).all()
    assert all(2 <= total <= 4 for _, total in per_department)
    confidential = set(
        db.execute(
            select(Category.department_id, Category.name).where(Category.is_confidential)
        ).tuples()
    )
    assert confidential == {
        ("HR", "Employee Records"),
        ("LEG", "Contract Review"),
        ("SEC", "Security Incident"),
    }
    assert count(db, ConfidentialGrant) == 2
    statuses = set(db.scalars(select(SignupRequest.status)))
    assert {status.value for status in statuses} == {"pending", "rejected"}


def test_seed_covers_every_status_and_level(db: Session, seeded: SeedResult) -> None:
    tickets = list(db.scalars(select(Ticket)))
    assert len(tickets) == seeded.tickets
    assert 15 <= len(tickets) <= 18
    assert {ticket.status for ticket in tickets} == set(TicketStatus)
    assert {ticket.escalation_level for ticket in tickets} == {0, 1, 2, 3}
    assert any(ticket.update_overdue for ticket in tickets)
    transferred = ticket_titled(db, "Onboarding documents for a new joiner")
    assert transferred.department_id == "HR"
    assert transferred.ticket_no.startswith("IBX-IT-")
    assigned = ticket_titled(db, "Excel add-in crashes on startup")
    assert assigned.assignee_id == user_by_name(db, "Dev Patel").id
    closed = ticket_titled(db, "Install Docker Desktop")
    assert closed.feedback_rating == 5
    assert count(db, Notification) > 0
    assert count(db, AuditLog) > len(tickets)
    assert count(db, EscalationEvent) > 0


def test_seed_is_idempotent(
    db: Session, seeded: SeedResult, settings: Settings, clock: FrozenClock
) -> None:
    before = (count(db, User), count(db, Ticket), count(db, AuditLog), count(db, Notification))
    again = seed(db, settings, clock)
    assert not again.created
    after = (count(db, User), count(db, Ticket), count(db, AuditLog), count(db, Notification))
    assert after == before
    assert seeded.created


def test_seeded_logins_work_or_fail_with_documented_codes(
    client: TestClient, db: Session, seeded: SeedResult
) -> None:
    assert seeded.created
    for person in PEOPLE:
        db.execute(delete(RateLimitHit))
        db.commit()
        response = client.post(LOGIN, json={"email": person.email, "password": SEED_PASSWORD})
        if person.state is AccountState.ACTIVE:
            assert response.status_code == 200, person.name
            continue
        assert response.status_code == 403, person.name
        error = response.json()["error"]
        assert error["code"] == "account_state"
        assert error["details"]["state"] == person.state.value
        if person.state is AccountState.REJECTED:
            assert error["details"]["rejection_reason"]
    rohan = client.post(
        LOGIN, json={"email": email_for("Rohan Mehta"), "password": "Wrong-Password-1"}
    )
    assert rohan.status_code == 401
    assert rohan.json()["error"]["code"] == "invalid_credentials"
    assert db.scalar(select(func.count()).select_from(User)) == len(PEOPLE)


def test_confidential_visibility_for_seeded_users(
    client: TestClient,
    db: Session,
    seeded: SeedResult,
    settings: Settings,
    clock: FrozenClock,
) -> None:
    assert seeded.created
    hr_ticket = ticket_titled(db, "Update personal records after a name change")
    legal_ticket = ticket_titled(db, "Review the renewal terms of the audit contract")
    assert hr_ticket.confidential
    assert legal_ticket.confidential

    def status_for(name: str, ticket: Ticket) -> int:
        token = create_access_token(user_by_name(db, name).id, clock.now(), settings).token
        response: Response = client.get(
            f"/api/v1/tickets/{ticket.ticket_no}", headers={"Authorization": f"Bearer {token}"}
        )
        status: int = response.status_code
        return status

    assert status_for("Neha Kapoor", hr_ticket) == 200
    assert status_for("Karan Shah", hr_ticket) == 200
    assert status_for("Asha Verma", hr_ticket) == 200
    assert status_for("Aarav Khanna", hr_ticket) == 404
    assert status_for("Priya Nair", hr_ticket) == 404
    assert status_for("Aarav Khanna", legal_ticket) == 404
    assert status_for("Priya Nair", legal_ticket) == 404
    leaked = db.scalars(
        select(Notification).where(
            Notification.ticket_id == hr_ticket.id,
            Notification.user_id.in_(
                [user_by_name(db, "Aarav Khanna").id, user_by_name(db, "Priya Nair").id]
            ),
        )
    ).first()
    assert leaked is None


def test_seed_refuses_in_prod(db: Session, clock: FrozenClock) -> None:
    prod = Settings(env=Environment.PROD, jwt_secret=SecretStr("p" * 40), cookie_secure=True)
    with pytest.raises(SeedRefused):
        seed(db, prod, clock)
    assert count(db, Department) == 0
