import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, event, text
from sqlalchemy.engine.interfaces import DBAPICursor, ExecutionContext
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.security import create_access_token
from scripts.perf_seed import DEFAULT_EVENTS, DEFAULT_TICKETS, PerfWorld, insert_perf_data
from tests.conftest import FROZEN_NOW

RUNS: Final = 20
WARMUP: Final = 2
P95_BUDGET_MS: Final = 300.0
TICKETS: Final = "/api/v1/tickets"
UNCOMMITTED_TABLES: Final = ("users", "spoke_assignments", "categories", "tickets", "ticket_events")


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    actor: str
    params: Mapping[str, str]
    index_only: bool = True


CASES: Final = (
    Case("employee_default_order", "employee", {}),
    Case("spoke_queue_default_order", "spoke", {"scope": "queue"}),
    Case(
        "spoke_queue_department_and_status",
        "spoke",
        {"scope": "queue", "department_id": "IT", "status": "in_progress"},
    ),
    Case(
        "admin_department_and_status",
        "admin",
        {"scope": "all", "department_id": "HR", "status": "new"},
    ),
    Case("admin_text_search", "admin", {"scope": "all", "q": "payroll"}),
    Case("spoke_text_search", "spoke", {"scope": "queue", "q": "payroll"}),
    Case("admin_all_default_order", "admin", {"scope": "all"}, index_only=False),
)


@pytest.fixture(scope="module")
def perf_connection(migrated_engine: Engine) -> Iterator[tuple[Connection, PerfWorld]]:
    connection = migrated_engine.connect()
    outer = connection.begin()
    for table in UNCOMMITTED_TABLES:
        connection.execute(text(f"LOCK TABLE {table} IN SHARE UPDATE EXCLUSIVE MODE"))
    world = insert_perf_data(connection, FROZEN_NOW, DEFAULT_TICKETS, DEFAULT_EVENTS)
    yield connection, world
    outer.rollback()
    connection.close()


@pytest.fixture
def db(perf_connection: tuple[Connection, PerfWorld]) -> Iterator[Session]:
    connection, _ = perf_connection
    nested = connection.begin_nested()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    yield session
    session.close()
    if nested.is_active:
        nested.rollback()


def headers_for(
    case: Case, world: PerfWorld, clock: FrozenClock, settings: Settings
) -> dict[str, str]:
    actors: dict[str, uuid.UUID] = {
        "employee": world.employee_id,
        "spoke": world.spoke_id,
        "admin": world.admin_id,
    }
    token = create_access_token(actors[case.actor], clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, int(len(ordered) * 0.95) - 1)]


def test_perf_data_volume(db: Session) -> None:
    tickets = db.scalar(text("SELECT count(*) FROM tickets"))
    events = db.scalar(text("SELECT count(*) FROM ticket_events"))
    assert tickets == DEFAULT_TICKETS
    assert events == DEFAULT_EVENTS


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_list_p95_under_budget(
    case: Case,
    client: TestClient,
    perf_connection: tuple[Connection, PerfWorld],
    clock: FrozenClock,
    settings: Settings,
) -> None:
    _, world = perf_connection
    headers = headers_for(case, world, clock, settings)
    samples: list[float] = []
    for attempt in range(WARMUP + RUNS):
        started = time.perf_counter()
        response = client.get(TICKETS, params=dict(case.params), headers=headers)
        elapsed = (time.perf_counter() - started) * 1000
        assert response.status_code == 200, response.text
        if attempt >= WARMUP:
            samples.append(elapsed)
    body = response.json()
    assert body["total"] > 0
    assert p95(samples) < P95_BUDGET_MS, f"{case.name}: p95 {p95(samples):.1f} ms"


@pytest.mark.parametrize(
    "case", [case for case in CASES if case.index_only], ids=lambda case: case.name
)
def test_list_queries_avoid_sequential_scans_on_tickets(
    case: Case,
    client: TestClient,
    perf_connection: tuple[Connection, PerfWorld],
    clock: FrozenClock,
    settings: Settings,
) -> None:
    connection, world = perf_connection
    captured: list[tuple[str, Mapping[str, object]]] = []

    def capture(
        _conn: Connection,
        _cursor: DBAPICursor,
        statement: str,
        parameters: object,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        selecting = statement.lstrip().upper().startswith("SELECT")
        if selecting and "FROM tickets" in statement and isinstance(parameters, dict):
            captured.append((statement, parameters))

    event.listen(connection, "before_cursor_execute", capture)
    try:
        response = client.get(
            TICKETS, params=dict(case.params), headers=headers_for(case, world, clock, settings)
        )
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert captured
    for statement, parameters in captured:
        plan = connection.exec_driver_sql(f"EXPLAIN {statement}", parameters).scalars().all()
        text_plan = "\n".join(str(line) for line in plan)
        assert "Seq Scan on tickets" not in text_plan, f"{case.name}\n{statement}\n{text_plan}"
