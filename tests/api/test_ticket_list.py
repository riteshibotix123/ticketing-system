from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.enums import Priority, Role, TicketStatus
from app.core.security import create_access_token
from app.models import User
from tests.factories import (
    FACTORY_NOW,
    TicketWorld,
    make_category,
    make_collaborator,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_ticket_world,
    make_user,
)

TICKETS = "/api/v1/tickets"


@pytest.fixture
def world(db: Session) -> TicketWorld:
    return make_ticket_world(db)


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def numbers(response: Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def keys_of(world: TicketWorld, response: Response) -> set[str]:
    by_number = {ticket.ticket_no: key for key, ticket in world.tickets.items()}
    return {by_number[number] for number in numbers(response) if number in by_number}


def get(
    client: TestClient,
    db: Session,
    user: User,
    clock: Clock,
    settings: Settings,
    params: Mapping[str, str | list[str]] | None = None,
) -> Response:
    response: Response = client.get(
        TICKETS, params=dict(params or {}), headers=bearer(db, user, clock, settings)
    )
    return response


@pytest.mark.parametrize(
    ("name", "scope", "expected"),
    [
        ("requester", "mine", {"normal", "secret", "hr", "closed"}),
        ("collaborator", "mine", {"normal", "secret"}),
        ("assignee", "mine", set()),
        ("assignee", "assigned", {"normal", "secret"}),
        ("requester", "assigned", set()),
        ("spoke", "queue", {"normal", "closed"}),
        ("spoke_with_grant", "queue", {"normal", "secret", "closed"}),
        ("other_spoke", "queue", {"hr"}),
        ("admin", "all", {"normal", "hr", "closed"}),
        ("admin_with_grant", "all", {"normal", "secret", "hr", "closed"}),
        ("super_admin", "all", {"normal", "secret", "hr", "closed"}),
        ("employee_with_grant", "mine", set()),
        ("unrelated", "mine", set()),
    ],
)
def test_scopes_apply_visibility(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    name: str,
    scope: str,
    expected: set[str],
) -> None:
    response = get(client, db, world.users[name], clock, settings, {"scope": scope})
    assert keys_of(world, response) == expected
    assert response.json()["total"] == len(expected)


def test_default_scope_is_mine(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    response = get(client, db, world.users["collaborator"], clock, settings)
    assert keys_of(world, response) == {"normal", "secret"}


@pytest.mark.parametrize("name", ["requester", "employee_with_grant", "admin", "super_admin"])
def test_queue_requires_spoke(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld, name: str
) -> None:
    response = get(client, db, world.users[name], clock, settings, {"scope": "queue"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_queue_department_narrowing(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    spoke = world.users["spoke"]
    make_spoke_assignment(db, spoke, world.hr)
    both = get(client, db, spoke, clock, settings, {"scope": "queue"})
    assert keys_of(world, both) == {"normal", "closed", "hr"}
    hr_only = get(client, db, spoke, clock, settings, {"scope": "queue", "department_id": "HR"})
    assert keys_of(world, hr_only) == {"hr"}
    other = get(
        client,
        db,
        world.users["other_spoke"],
        clock,
        settings,
        {"scope": "queue", "department_id": "IT"},
    )
    assert other.status_code == 403


@pytest.mark.parametrize("name", ["requester", "spoke", "employee_with_grant"])
def test_all_requires_view_all_flag(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld, name: str
) -> None:
    response = get(client, db, world.users[name], clock, settings, {"scope": "all"})
    assert response.status_code == 403


def test_items_carry_sla_and_allowed_actions(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    response = get(client, db, world.users["spoke"], clock, settings, {"scope": "queue"})
    item = next(i for i in response.json()["items"] if i["id"] == world.tickets["normal"].ticket_no)
    assert set(item["sla"]) == {"level", "kind", "paused", "stopped", "due_at", "label"}
    assert "resolve" in item["allowed_actions"]
    assert item["category_name"] == "Hardware"
    assert [c["name"] for c in item["collaborators"]] == ["Collaborator"]


def test_hidden_tickets_never_counted(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    for params in (
        {"scope": "all"},
        {"scope": "all", "confidential": "true"},
        {"scope": "all", "q": "Sensitive"},
        {"scope": "all", "category_id": str(world.secret_category.id)},
    ):
        response = get(client, db, world.users["admin"], clock, settings, params)
        body = response.json()
        assert world.tickets["secret"].ticket_no not in numbers(response)
        assert body["total"] == len(body["items"])


@dataclass(frozen=True)
class Spec:
    key: str
    status: TicketStatus
    title: str
    priority: Priority = Priority.MEDIUM
    escalation_level: int = 0
    update_overdue: bool = False
    eta: datetime | None = None
    confidential: bool = False
    department: str = "IT"
    assigned: bool = False


SPECS = (
    Spec("new_low", TicketStatus.NEW, "Mouse broken", priority=Priority.LOW),
    Spec("new_critical", TicketStatus.NEW, "Server down", priority=Priority.CRITICAL),
    Spec("warning", TicketStatus.IN_PROGRESS, "VPN slow", escalation_level=1, assigned=True),
    Spec("breached", TicketStatus.ACKNOWLEDGED, "Email 50% loss", escalation_level=2),
    Spec("l3", TicketStatus.ASSIGNED, "Printer jam", escalation_level=3),
    Spec("stale", TicketStatus.IN_PROGRESS, "Monitor", update_overdue=True),
    Spec("overdue_eta", TicketStatus.IN_PROGRESS, "Keyboard", eta=FACTORY_NOW - timedelta(hours=1)),
    Spec("resolved", TicketStatus.RESOLVED, "Docking", priority=Priority.HIGH),
    Spec("hr_private", TicketStatus.NEW, "Private", confidential=True, department="HR"),
)
ALL_KEYS = {spec.key for spec in SPECS}
ACTIVE_KEYS = ALL_KEYS - {"resolved"}


@dataclass(frozen=True)
class Board:
    boss: User
    requester: User
    assignee: User
    numbers: dict[str, str]
    category_id: str

    def keys(self, response: Response) -> list[str]:
        by_number = {number: key for key, number in self.numbers.items()}
        return [by_number[number] for number in numbers(response)]


@pytest.fixture
def board(db: Session) -> Board:
    departments = {"IT": make_department(db, "IT"), "HR": make_department(db, "HR")}
    boss = make_user(db, departments["IT"], role=Role.SUPER_ADMIN)
    requester = make_user(db, departments["IT"])
    other_requester = make_user(db, departments["IT"])
    assignee = make_user(db, departments["IT"])
    category = make_category(db, departments["IT"], "Peripherals")
    numbers_by_key: dict[str, str] = {}
    for index, spec in enumerate(SPECS):
        ticket = make_ticket(
            db,
            requester if index % 2 == 0 else other_requester,
            departments[spec.department],
            status=spec.status,
            priority=spec.priority,
            title=spec.title,
            escalation_level=spec.escalation_level,
            update_overdue=spec.update_overdue,
            eta=spec.eta or FACTORY_NOW + timedelta(days=5),
            confidential=spec.confidential,
            assignee=assignee if spec.assigned else None,
            category=category if spec.key == "new_low" else None,
            at=FACTORY_NOW - timedelta(days=20 - index),
        )
        numbers_by_key[spec.key] = ticket.ticket_no
    return Board(boss, requester, assignee, numbers_by_key, str(category.id))


def list_all(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    board: Board,
    params: dict[str, str | list[str]],
) -> Response:
    return get(client, db, board.boss, clock, settings, {"scope": "all", **params})


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"status": "open"}, ACTIVE_KEYS),
        ({"status": "resolved"}, {"resolved"}),
        ({"status": ["new", "resolved"]}, {"new_low", "new_critical", "hr_private", "resolved"}),
        ({"status[]": ["acknowledged", "assigned"]}, {"breached", "l3"}),
        ({"priority": "critical"}, {"new_critical"}),
        ({"priority[]": ["low", "high"]}, {"new_low", "resolved"}),
        ({"department_id": "HR"}, {"hr_private"}),
        ({"sla_state": "unacknowledged"}, {"new_low", "new_critical", "hr_private"}),
        ({"sla_state": "warning"}, {"warning"}),
        ({"sla_state": "breached"}, {"breached", "l3"}),
        ({"sla_state": "stale"}, {"stale"}),
        ({"escalation_level": "3"}, {"l3"}),
        ({"escalation_level": "0"}, ALL_KEYS - {"warning", "breached", "l3"}),
        ({"confidential": "true"}, {"hr_private"}),
        ({"confidential": "false"}, ALL_KEYS - {"hr_private"}),
        ({"overdue_eta": "true"}, {"overdue_eta"}),
        ({"q": "server"}, {"new_critical"}),
        ({"q": "50%"}, {"breached"}),
        ({"q": "IBX-HR"}, {"hr_private"}),
        ({"created_from": "2026-10-13T04:30:00Z"}, {"overdue_eta", "resolved", "hr_private"}),
        ({"created_to": "2026-10-08T04:30:00Z"}, {"new_low", "new_critical"}),
    ],
)
def test_filters(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    board: Board,
    params: dict[str, str | list[str]],
    expected: set[str],
) -> None:
    assert set(board.keys(list_all(client, db, clock, settings, board, params))) == expected


def test_filter_by_people_and_category(
    client: TestClient, db: Session, clock: Clock, settings: Settings, board: Board
) -> None:
    by_requester = list_all(
        client, db, clock, settings, board, {"requester_id": str(board.requester.id)}
    )
    assert set(board.keys(by_requester)) == {spec.key for spec in SPECS[::2]}
    by_assignee = list_all(
        client, db, clock, settings, board, {"assignee_id": str(board.assignee.id)}
    )
    assert board.keys(by_assignee) == ["warning"]
    by_category = list_all(client, db, clock, settings, board, {"category_id": board.category_id})
    assert board.keys(by_category) == ["new_low"]


@pytest.mark.parametrize(
    "params",
    [
        {"status": "bogus"},
        {"priority": "urgent"},
        {"sla_state": "late"},
        {"escalation_level": "4"},
        {"category_id": "not-a-uuid"},
        {"requester_id": "nope"},
        {"sort": "requester"},
        {"scope": "everything"},
        {"page_size": "101"},
    ],
)
def test_invalid_query_values(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    board: Board,
    params: dict[str, str | list[str]],
) -> None:
    response = list_all(client, db, clock, settings, board, params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_default_urgency_order(
    client: TestClient, db: Session, clock: Clock, settings: Settings, board: Board
) -> None:
    keys = board.keys(list_all(client, db, clock, settings, board, {}))
    assert keys == [
        "l3",
        "breached",
        "warning",
        "new_critical",
        "stale",
        "overdue_eta",
        "hr_private",
        "new_low",
        "resolved",
    ]


@pytest.mark.parametrize(
    ("sort", "first", "last"),
    [
        ("created_at", "new_low", "hr_private"),
        ("-created_at", "hr_private", "new_low"),
        ("priority", "new_low", "new_critical"),
        ("-priority", "new_critical", "new_low"),
        ("title", "resolved", "warning"),
        ("status", "breached", "resolved"),
    ],
)
def test_sort_whitelist(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    board: Board,
    sort: str,
    first: str,
    last: str,
) -> None:
    keys = board.keys(list_all(client, db, clock, settings, board, {"sort": sort}))
    assert (keys[0], keys[-1]) == (first, last)


def test_paging(
    client: TestClient, db: Session, clock: Clock, settings: Settings, board: Board
) -> None:
    response = list_all(client, db, clock, settings, board, {"page": "2", "page_size": "4"})
    body = response.json()
    assert (body["total"], body["page"], body["page_size"], len(body["items"])) == (9, 2, 4, 4)


@contextmanager
def count_queries(engine: Engine) -> Iterator[list[str]]:
    statements: list[str] = []

    def record(
        _conn: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_query_count_is_constant(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    migrated_engine: Engine,
    world: TicketWorld,
) -> None:
    for index in range(12):
        ticket = make_ticket(
            db,
            world.users["requester"],
            world.it,
            status=TicketStatus.IN_PROGRESS,
            category=world.normal_category,
        )
        make_collaborator(db, ticket, world.users["unrelated" if index % 2 else "collaborator"])
    headers = bearer(db, world.users["super_admin"], clock, settings)
    counts = []
    for size in ("2", "16"):
        with count_queries(migrated_engine) as statements:
            response = client.get(
                TICKETS, params={"scope": "all", "page_size": size}, headers=headers
            )
        assert response.status_code == 200
        counts.append(len(statements))
    assert counts[0] == counts[1]


def test_unassigned_and_awaiting_before_filters(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    long_wait = make_ticket(
        db,
        requester,
        world.it,
        status=TicketStatus.AWAITING_REQUESTER,
        at=FACTORY_NOW - timedelta(days=3),
    )
    make_ticket(
        db,
        requester,
        world.it,
        status=TicketStatus.AWAITING_REQUESTER,
        at=FACTORY_NOW - timedelta(hours=1),
    )
    fresh = make_ticket(db, requester, world.it)
    admin = world.users["admin"]
    unassigned = get(client, db, admin, clock, settings, {"scope": "all", "unassigned": "true"})
    assert set(numbers(unassigned)) == {world.tickets["hr"].ticket_no, fresh.ticket_no}
    cutoff = (FACTORY_NOW - timedelta(hours=48)).isoformat()
    waiting = get(client, db, admin, clock, settings, {"scope": "all", "awaiting_before": cutoff})
    assert numbers(waiting) == [long_wait.ticket_no]
    naive = get(
        client, db, admin, clock, settings, {"scope": "all", "awaiting_before": "2026-10-25T00:00"}
    )
    assert naive.status_code == 422
