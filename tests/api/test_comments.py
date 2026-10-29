from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import Role, TicketStatus
from app.core.events import (
    CommentAdded,
    DomainEvent,
    TeamUpdateRecorded,
    TicketStatusChanged,
    bus,
)
from app.core.security import create_access_token
from app.models import (
    AuditLog,
    Department,
    SlaTimer,
    Ticket,
    TicketEvent,
    TicketEventKind,
    TimerKind,
    User,
)
from tests.factories import (
    make_collaborator,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_timer,
    make_user,
)

TICKETS = "/api/v1/tickets"
NOTE = "Checked the logs, looks like a driver issue"


@dataclass(frozen=True)
class Team:
    it: Department
    requester: User
    spoke: User
    assignee: User
    collaborator: User
    admin: User
    outsider: User


@pytest.fixture
def team(db: Session) -> Team:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    spoke = make_user(db, it, name="Sam Spoke")
    make_spoke_assignment(db, spoke, it)
    return Team(
        it=it,
        requester=make_user(db, hr, name="Rita Requester"),
        spoke=spoke,
        assignee=make_user(db, hr, name="Andy Assignee"),
        collaborator=make_user(db, hr, name="Cora Collaborator"),
        admin=make_user(db, hr, role=Role.ADMIN, name="Ada Admin"),
        outsider=make_user(db, hr, name="Otto Outsider"),
    )


def ticket_in(db: Session, team: Team, status: TicketStatus) -> Ticket:
    ticket = make_ticket(
        db, team.requester, team.it, status=status, owner=team.spoke, assignee=team.assignee
    )
    make_collaborator(db, ticket, team.collaborator)
    return ticket


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def comment(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    user: User,
    ticket: Ticket,
    body: Mapping[str, object],
) -> Response:
    response: Response = client.post(
        f"{TICKETS}/{ticket.ticket_no}/comments",
        json=body,
        headers=bearer(db, user, clock, settings),
    )
    return response


def timeline(
    client: TestClient, db: Session, clock: Clock, settings: Settings, user: User, ticket: Ticket
) -> list[dict[str, object]]:
    response = client.get(
        f"{TICKETS}/{ticket.ticket_no}/timeline", headers=bearer(db, user, clock, settings)
    )
    assert response.status_code == 200
    items: list[dict[str, object]] = response.json()
    return items


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


def capture(*event_types: type[DomainEvent]) -> list[DomainEvent]:
    seen: list[DomainEvent] = []
    for event_type in event_types:
        bus.register(event_type, lambda _session, event: seen.append(event))
    return seen


def events_of(db: Session, ticket: Ticket) -> list[TicketEvent]:
    statement = select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
    return list(db.scalars(statement.order_by(TicketEvent.at, TicketEvent.kind)))


def progress_timer(db: Session, ticket: Ticket) -> SlaTimer:
    statement = select(SlaTimer).where(
        SlaTimer.ticket_id == ticket.id, SlaTimer.kind == TimerKind.PROGRESS_UPDATE
    )
    return db.scalars(statement).one()


def test_public_comment_by_assignee(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    seen = capture(CommentAdded, TeamUpdateRecorded)
    response = comment(
        client, db, clock, settings, team.assignee, ticket, {"body": "  On it now  "}
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["type"] == "comment"
    assert payload["body"] == "On it now"
    assert payload["public"] is True
    assert payload["at"] == "2026-10-27T04:30:00Z"
    assert payload["actor"]["id"] == str(team.assignee.id)
    assert "action" not in payload
    [event] = events_of(db, ticket)
    assert (event.kind, event.is_public, event.actor_id) == (
        TicketEventKind.COMMENT,
        True,
        team.assignee.id,
    )
    assert str(event.id) == payload["id"]
    db.refresh(ticket)
    assert ticket.last_team_update_at == clock.now()
    added = seen[0]
    assert isinstance(added, CommentAdded)
    assert (added.internal, added.ticket_event_id) == (False, event.id)
    assert isinstance(seen[1], TeamUpdateRecorded)


def test_internal_note_by_spoke(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    seen = capture(CommentAdded, TeamUpdateRecorded)
    response = comment(
        client, db, clock, settings, team.spoke, ticket, {"body": NOTE, "internal": True}
    )
    assert response.status_code == 201
    assert response.json()["type"] == "internal_note"
    assert response.json()["public"] is False
    added = seen[0]
    assert isinstance(added, CommentAdded)
    assert added.internal is True
    assert isinstance(seen[1], TeamUpdateRecorded)


@pytest.mark.parametrize("who", ["requester", "collaborator"])
def test_participant_comment_is_not_team_update(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    who: str,
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    seen = capture(CommentAdded, TeamUpdateRecorded)
    user: User = getattr(team, who)
    response = comment(client, db, clock, settings, user, ticket, {"body": "Any news?"})
    assert response.status_code == 201
    assert [type(event) for event in seen] == [CommentAdded]
    db.refresh(ticket)
    assert ticket.last_team_update_at != clock.now()


@pytest.mark.parametrize(
    ("who", "internal", "status", "expected"),
    [
        ("requester", True, TicketStatus.IN_PROGRESS, 403),
        ("collaborator", True, TicketStatus.IN_PROGRESS, 403),
        ("outsider", False, TicketStatus.IN_PROGRESS, 404),
        ("admin", True, TicketStatus.NEW, 201),
        ("requester", False, TicketStatus.RESOLVED, 201),
        ("requester", False, TicketStatus.CLOSED, 409),
        ("assignee", True, TicketStatus.CLOSED, 409),
        ("spoke", False, TicketStatus.CANCELLED, 409),
    ],
)
def test_comment_permissions(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    who: str,
    internal: bool,
    status: TicketStatus,
    expected: int,
) -> None:
    ticket = ticket_in(db, team, status)
    user: User = getattr(team, who)
    body = {"body": "A message", "internal": internal}
    response = comment(client, db, clock, settings, user, ticket, body)
    assert response.status_code == expected
    if expected == 403:
        assert error_code(response) == "forbidden"
    if expected == 409:
        assert error_code(response) == "invalid_transition"
    if expected != 201:
        assert events_of(db, ticket) == []


@pytest.mark.parametrize("body", [{"body": "   "}, {"body": "x" * 5001}, {"internal": False}])
def test_comment_validation(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    body: Mapping[str, object],
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    response = comment(client, db, clock, settings, team.spoke, ticket, body)
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"body"}


def test_internal_note_hidden_from_requester_and_collaborator(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    body = {"body": NOTE, "internal": True}
    assert comment(client, db, clock, settings, team.assignee, ticket, body).status_code == 201
    public = {"body": "We are looking into it"}
    assert comment(client, db, clock, settings, team.spoke, ticket, public).status_code == 201
    for user in (team.requester, team.collaborator):
        items = timeline(client, db, clock, settings, user, ticket)
        assert [item["type"] for item in items] == ["comment"]
        assert all(item["body"] != NOTE for item in items)
    for user in (team.spoke, team.assignee, team.admin):
        items = timeline(client, db, clock, settings, user, ticket)
        assert sorted(str(item["type"]) for item in items) == ["comment", "internal_note"]


def test_requester_reply_resumes_awaiting_ticket(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.AWAITING_REQUESTER)
    seen = capture(TicketStatusChanged, CommentAdded, TeamUpdateRecorded)
    response = comment(
        client, db, clock, settings, team.requester, ticket, {"body": "Here is the screenshot"}
    )
    assert response.status_code == 201
    db.refresh(ticket)
    assert ticket.status is TicketStatus.IN_PROGRESS
    assert ticket.awaiting_since is None
    system = next(event for event in events_of(db, ticket) if event.action == "status_changed")
    assert (system.actor_id, system.is_public) == (None, True)
    assert [type(event) for event in seen] == [TicketStatusChanged, CommentAdded]
    changed = seen[0]
    assert isinstance(changed, TicketStatusChanged)
    assert (changed.from_status, changed.to_status) == (
        TicketStatus.AWAITING_REQUESTER,
        TicketStatus.IN_PROGRESS,
    )
    actions = db.scalars(select(AuditLog.action).where(AuditLog.ticket_id == ticket.id))
    assert list(actions) == ["ticket_status_changed"]
    items = timeline(client, db, clock, settings, team.requester, ticket)
    assert {str(item["type"]) for item in items} == {"comment", "audit"}


@pytest.mark.parametrize(
    ("who", "internal"), [("collaborator", False), ("assignee", False), ("assignee", True)]
)
def test_other_replies_do_not_resume(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    who: str,
    internal: bool,
) -> None:
    ticket = ticket_in(db, team, TicketStatus.AWAITING_REQUESTER)
    user: User = getattr(team, who)
    body = {"body": "A message", "internal": internal}
    assert comment(client, db, clock, settings, user, ticket, body).status_code == 201
    db.refresh(ticket)
    assert ticket.status is TicketStatus.AWAITING_REQUESTER


@pytest.mark.parametrize(
    ("who", "internal", "resets"),
    [
        ("assignee", False, True),
        ("spoke", True, True),
        ("requester", False, False),
        ("collaborator", False, False),
    ],
)
def test_update_timer_resets_only_for_team(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    who: str,
    internal: bool,
    resets: bool,
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    started = clock.now() - timedelta(hours=10)
    make_timer(db, ticket, TimerKind.PROGRESS_UPDATE, started_at=started)
    user: User = getattr(team, who)
    body = {"body": "A message", "internal": internal}
    assert comment(client, db, clock, settings, user, ticket, body).status_code == 201
    db.expire_all()
    timer = progress_timer(db, ticket)
    assert (timer.started_at == clock.now()) is resets
    assert (timer.cycle == 2) is resets
