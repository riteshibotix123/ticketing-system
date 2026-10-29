import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Role, TicketStatus
from app.core.errors import ApiError, ErrorCode
from app.core.events import (
    DomainEvent,
    TeamUpdateRecorded,
    TicketAcknowledged,
    TicketAssigned,
    TicketStatusChanged,
    bus,
)
from app.core.security import create_access_token
from app.models import AuditLog, Department, SlaTimer, Ticket, TicketEvent, TimerKind, User
from app.policy.actors import load_actor
from app.schemas.workflow import AcknowledgeBody
from app.services.handlers import register_all
from app.services.workflow.progress import ProgressService
from tests.factories import (
    FACTORY_NOW,
    make_collaborator,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_timer,
    make_user,
)

TICKETS = "/api/v1/tickets"
REASON = "Needs a specialist"


@dataclass(frozen=True)
class Team:
    it: Department
    hr: Department
    requester: User
    spoke: User
    second_spoke: User
    member: User
    admin: User
    super_admin: User
    outsider: User
    hr_spoke: User


@pytest.fixture
def team(db: Session) -> Team:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    spoke = make_user(db, it, name="Sam Spoke")
    second_spoke = make_user(db, hr, name="Second Spoke")
    hr_spoke = make_user(db, hr, name="Hr Spoke")
    make_spoke_assignment(db, spoke, it)
    make_spoke_assignment(db, second_spoke, it)
    make_spoke_assignment(db, hr_spoke, hr)
    return Team(
        it=it,
        hr=hr,
        requester=make_user(db, hr, name="Rita Requester"),
        spoke=spoke,
        second_spoke=second_spoke,
        member=make_user(db, it, name="Mia Member"),
        admin=make_user(db, hr, role=Role.ADMIN, name="Ada Admin"),
        super_admin=make_user(db, hr, role=Role.SUPER_ADMIN, name="Sue Super"),
        outsider=make_user(db, hr, name="Otto Outsider"),
        hr_spoke=hr_spoke,
    )


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def post(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    user: User,
    ticket: Ticket,
    action: str,
    body: Mapping[str, object],
) -> Response:
    response: Response = client.post(
        f"{TICKETS}/{ticket.ticket_no}/{action}",
        json=body,
        headers=bearer(db, user, clock, settings),
    )
    return response


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


def fields(response: Response) -> dict[str, str]:
    assert response.status_code == 422
    result = response.json()["error"]["fields"]
    assert isinstance(result, dict)
    return result


def capture(*event_types: type[DomainEvent]) -> list[DomainEvent]:
    seen: list[DomainEvent] = []
    for event_type in event_types:
        bus.register(event_type, lambda _session, event: seen.append(event))
    return seen


def iso(clock: Clock, delta: timedelta) -> str:
    return (clock.now() + delta).isoformat().replace("+00:00", "Z")


def events_of(db: Session, ticket: Ticket) -> list[TicketEvent]:
    statement = select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
    return list(db.scalars(statement.order_by(TicketEvent.at, TicketEvent.id)))


def audit_of(db: Session, ticket: Ticket, action: str) -> AuditLog:
    statement = select(AuditLog).where(AuditLog.ticket_id == ticket.id, AuditLog.action == action)
    return db.scalars(statement).one()


def test_acknowledge_with_eta(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(db, team.requester, team.it)
    make_timer(db, ticket)
    seen = capture(TicketAcknowledged, TeamUpdateRecorded)
    response = post(
        client,
        db,
        clock,
        settings,
        team.spoke,
        ticket,
        "acknowledge",
        {"eta": iso(clock, timedelta(days=1))},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "acknowledged"
    assert body["owner"]["id"] == str(team.spoke.id)
    assert body["acknowledged_at"] == "2026-10-27T04:30:00Z"
    assert body["last_team_update_at"] == "2026-10-27T04:30:00Z"
    assert body["eta"] == "2026-10-28T04:30:00Z"
    assert body["next_checkpoint_at"] is None
    assert "acknowledge" not in body["allowed_actions"]
    assert "assign" in body["allowed_actions"]
    [event] = events_of(db, ticket)
    assert event.action == "acknowledged"
    assert event.is_public is True
    assert event.detail == "Acknowledged by Sam Spoke. ETA 28 Oct 2026, 10:00 IST"
    entry = audit_of(db, ticket, "ticket_acknowledged")
    assert entry.actor_id == team.spoke.id
    assert [type(event) for event in seen] == [TicketAcknowledged, TeamUpdateRecorded]
    timer = db.scalars(
        select(SlaTimer).where(
            SlaTimer.ticket_id == ticket.id, SlaTimer.kind == TimerKind.INITIAL_RESPONSE
        )
    ).one()
    assert timer.met_at == clock.now()


def test_acknowledge_without_eta(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(db, team.requester, team.it)
    response = post(
        client,
        db,
        clock,
        settings,
        team.spoke,
        ticket,
        "acknowledge",
        {
            "no_eta_reason": "Waiting for parts",
            "next_checkpoint_at": iso(clock, timedelta(hours=6)),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eta"] is None
    assert body["next_checkpoint_at"] == "2026-10-27T10:30:00Z"
    [event] = events_of(db, ticket)
    assert event.data is not None
    assert event.data["no_eta_reason"] == "Waiting for parts"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, {"no_eta_reason", "next_checkpoint_at"}),
        ({"eta": "2026-10-27T04:00:00Z"}, {"eta"}),
        ({"no_eta_reason": "Waiting for parts"}, {"next_checkpoint_at"}),
        ({"next_checkpoint_at": "2026-10-28T04:00:00Z"}, {"no_eta_reason"}),
        (
            {"no_eta_reason": "Waiting for parts", "next_checkpoint_at": "2026-10-27T04:30:00Z"},
            {"next_checkpoint_at"},
        ),
        ({"no_eta_reason": "abc", "next_checkpoint_at": "2026-10-28T04:00:00Z"}, {"no_eta_reason"}),
        ({"eta": "2026-10-28T04:00:00"}, {"eta"}),
    ],
)
def test_acknowledge_validation(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    body: dict[str, object],
    expected: set[str],
) -> None:
    ticket = make_ticket(db, team.requester, team.it)
    response = post(client, db, clock, settings, team.spoke, ticket, "acknowledge", body)
    assert set(fields(response)) == expected
    db.refresh(ticket)
    assert ticket.status is TicketStatus.NEW


@pytest.mark.parametrize(
    ("name", "status_code"),
    [
        ("spoke", 200),
        ("admin", 200),
        ("super_admin", 200),
        ("requester", 403),
        ("member", 404),
        ("outsider", 404),
        ("hr_spoke", 404),
    ],
)
def test_acknowledge_actor_classes(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    name: str,
    status_code: int,
) -> None:
    ticket = make_ticket(db, team.requester, team.it)
    user = getattr(team, name)
    body = {"eta": iso(clock, timedelta(days=1))}
    response = post(client, db, clock, settings, user, ticket, "acknowledge", body)
    assert response.status_code == status_code
    if status_code == 403:
        assert error_code(response) == "forbidden"
    if status_code == 404:
        assert error_code(response) == "not_found"


def test_requester_who_is_spoke_cannot_acknowledge(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(db, team.spoke, team.it)
    body = {"eta": iso(clock, timedelta(days=1))}
    response = post(client, db, clock, settings, team.spoke, ticket, "acknowledge", body)
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


@pytest.mark.parametrize(
    "status", [TicketStatus.ACKNOWLEDGED, TicketStatus.IN_PROGRESS, TicketStatus.CLOSED]
)
def test_acknowledge_wrong_status(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    status: TicketStatus,
) -> None:
    ticket = make_ticket(db, team.requester, team.it, status=status, owner=team.spoke)
    body = {"eta": iso(clock, timedelta(days=1))}
    response = post(client, db, clock, settings, team.second_spoke, ticket, "acknowledge", body)
    assert response.status_code == 409
    assert error_code(response) == "invalid_transition"


def test_unknown_ticket_is_not_found(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    response = client.post(
        f"{TICKETS}/IBX-IT-2026-999999/acknowledge",
        json={"eta": iso(clock, timedelta(days=1))},
        headers=bearer(db, team.spoke, clock, settings),
    )
    assert response.status_code == 404


def test_assign_to_department_member(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(
        db, team.requester, team.it, status=TicketStatus.ACKNOWLEDGED, owner=team.spoke
    )
    seen = capture(TicketAssigned, TicketStatusChanged)
    body = {"assignee_id": str(team.member.id)}
    response = post(client, db, clock, settings, team.spoke, ticket, "assign", body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "assigned"
    assert payload["assignee"]["id"] == str(team.member.id)
    [event] = events_of(db, ticket)
    assert (event.action, event.detail, event.is_public) == (
        "assigned",
        "Assigned to Mia Member",
        True,
    )
    entry = audit_of(db, ticket, "ticket_assigned")
    assert entry.reason is None
    assert [type(event) for event in seen] == [TicketAssigned, TicketStatusChanged]


def test_assign_to_spoke_of_department(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(
        db, team.requester, team.it, status=TicketStatus.IN_PROGRESS, owner=team.spoke
    )
    seen = capture(TicketStatusChanged)
    body = {"assignee_id": str(team.second_spoke.id)}
    response = post(client, db, clock, settings, team.spoke, ticket, "assign", body)
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert seen == []


def test_spoke_cannot_assign_outside_department(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(
        db, team.requester, team.it, status=TicketStatus.ACKNOWLEDGED, owner=team.spoke
    )
    body = {"assignee_id": str(team.outsider.id), "reason": REASON}
    response = post(client, db, clock, settings, team.spoke, ticket, "assign", body)
    assert set(fields(response)) == {"assignee_id"}


def test_admin_assigns_anyone_with_reason(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(
        db, team.requester, team.it, status=TicketStatus.ACKNOWLEDGED, owner=team.spoke
    )
    body: dict[str, object] = {"assignee_id": str(team.outsider.id)}
    missing = post(client, db, clock, settings, team.admin, ticket, "assign", body)
    assert set(fields(missing)) == {"reason"}
    body["reason"] = REASON
    response = post(client, db, clock, settings, team.admin, ticket, "assign", body)
    assert response.status_code == 200
    assert response.json()["assignee"]["id"] == str(team.outsider.id)
    assert audit_of(db, ticket, "ticket_assigned").reason == REASON
    [event] = events_of(db, ticket)
    assert event.detail == f"Assigned to Otto Outsider. Reason: {REASON}"
    assert event.public_detail == "Assigned to Otto Outsider"


def test_assign_validation(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(
        db,
        team.requester,
        team.it,
        status=TicketStatus.IN_PROGRESS,
        owner=team.spoke,
        assignee=team.member,
    )
    inactive = make_user(db, team.it, state=AccountState.DEACTIVATED)
    for assignee_id in (str(team.member.id), str(inactive.id), str(uuid.uuid4()), "nope"):
        body = {"assignee_id": assignee_id}
        response = post(client, db, clock, settings, team.spoke, ticket, "assign", body)
        assert set(fields(response)) == {"assignee_id"}
    short = {"assignee_id": str(team.second_spoke.id), "reason": "abc"}
    assert set(fields(post(client, db, clock, settings, team.spoke, ticket, "assign", short))) == {
        "reason"
    }


def test_assign_denials(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    fresh = make_ticket(db, team.requester, team.it)
    body = {"assignee_id": str(team.member.id)}
    response = post(client, db, clock, settings, team.spoke, fresh, "assign", body)
    assert response.status_code == 409
    assert error_code(response) == "invalid_transition"
    working = make_ticket(
        db,
        team.requester,
        team.it,
        status=TicketStatus.IN_PROGRESS,
        owner=team.spoke,
        assignee=team.outsider,
    )
    make_collaborator(db, working, team.hr_spoke)
    for user in (team.requester, team.outsider, team.hr_spoke):
        response = post(client, db, clock, settings, user, working, "assign", body)
        assert response.status_code == 403
        assert error_code(response) == "forbidden"


def test_assign_from_reopened_starts_work_cycle(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(
        db, team.requester, team.it, status=TicketStatus.REOPENED, owner=team.spoke
    )
    body = {"assignee_id": str(team.member.id)}
    response = post(client, db, clock, settings, team.spoke, ticket, "assign", body)
    assert response.status_code == 200
    assert response.json()["status"] == "assigned"
    progress = db.scalars(
        select(SlaTimer).where(
            SlaTimer.ticket_id == ticket.id, SlaTimer.kind == TimerKind.PROGRESS_UPDATE
        )
    ).one()
    assert progress.stopped_at is None


def test_concurrent_acknowledgements(committed_db: Session, test_database_url: str) -> None:
    register_all()
    it = make_department(committed_db, "IT")
    spokes = [make_user(committed_db, it) for _ in range(2)]
    for spoke in spokes:
        make_spoke_assignment(committed_db, spoke, it)
    ticket = make_ticket(committed_db, make_user(committed_db, it), it)
    committed_db.commit()
    engine = create_engine(test_database_url, pool_size=2, max_overflow=0)
    barrier = threading.Barrier(2, timeout=60)
    outcomes: list[str] = []
    lock = threading.Lock()
    clock = FrozenClock(FACTORY_NOW)
    body = AcknowledgeBody(eta=FACTORY_NOW + timedelta(days=1))

    def acknowledge(user_id: uuid.UUID) -> None:
        with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
            actor = load_actor(session, user_id)
            assert actor is not None
            barrier.wait()
            try:
                ProgressService(session, clock).acknowledge(actor, ticket.ticket_no, body)
                session.commit()
                result = "ok"
            except ApiError as exc:
                session.rollback()
                result = exc.code.value
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=acknowledge, args=(spoke.id,)) for spoke in spokes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    engine.dispose()
    assert sorted(outcomes) == sorted(["ok", ErrorCode.INVALID_TRANSITION.value])
    committed_db.expire_all()
    stored = committed_db.get(Ticket, ticket.id)
    assert stored is not None
    assert stored.status is TicketStatus.ACKNOWLEDGED
    assert stored.owner_id in {spoke.id for spoke in spokes}
    assert len(events_of(committed_db, stored)) == 1
