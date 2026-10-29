import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.security import create_access_token
from scripts.perf_seed import DEFAULT_EVENTS, DEFAULT_TICKETS, PerfWorld, insert_perf_data
from tests.conftest import FROZEN_NOW

RUNS: Final = 5
WARMUP: Final = 1
P95_BUDGET_MS: Final = 500.0
LOCKED_TABLES: Final = (
    "users",
    "spoke_assignments",
    "categories",
    "tickets",
    "ticket_events",
    "escalation_events",
)
KPI_DATA: Final = (
    """
    UPDATE tickets SET acknowledged_at = created_at + interval '2 hours'
    WHERE status <> 'new' AND title LIKE 'Perf ticket %'
    """,
    """
    INSERT INTO ticket_events (id, ticket_id, at, kind, action, is_public)
    SELECT gen_random_uuid(), id, created_at + interval '2 hours', 'audit', 'acknowledged', true
    FROM tickets WHERE status <> 'new' AND title LIKE 'Perf ticket %'
    UNION ALL
    SELECT gen_random_uuid(), id, created_at + interval '20 hours', 'audit', 'resolved', true
    FROM tickets WHERE status IN ('resolved', 'closed', 'reopened')
      AND title LIKE 'Perf ticket %'
    UNION ALL
    SELECT gen_random_uuid(), id, created_at + interval '30 hours', 'audit', 'reopened', true
    FROM tickets WHERE status = 'reopened' AND title LIKE 'Perf ticket %'
    """,
    """
    INSERT INTO escalation_events (id, ticket_id, timer_kind, cycle, level, step_key, at,
                                   recipient_ids)
    SELECT gen_random_uuid(), id, kind, 1, 2, 'L2', created_at + interval '24 hours', '{}'
    FROM tickets, unnest(ARRAY['initial_response', 'eta']) AS kind
    WHERE escalation_level >= 2 AND title LIKE 'Perf ticket %'
    """,
    "ANALYZE tickets",
    "ANALYZE ticket_events",
    "ANALYZE escalation_events",
)


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    actor: str
    path: str
    params: Mapping[str, str]


CASES: Final = (
    Case("admin_kpis_default", "admin", "/api/v1/reports/kpis", {}),
    Case(
        "admin_kpis_filtered",
        "admin",
        "/api/v1/reports/kpis",
        {"department_id": "HR", "priority[]": "high", "from": "2026-08-01T00:00:00Z"},
    ),
    Case("spoke_kpis_default", "spoke", "/api/v1/reports/kpis", {}),
    Case("admin_dashboard", "admin", "/api/v1/dashboard/admin", {}),
    Case("spoke_dashboard", "spoke", "/api/v1/dashboard/spoke", {}),
)


@pytest.fixture(scope="module")
def perf_connection(migrated_engine: Engine) -> Iterator[tuple[Connection, PerfWorld]]:
    connection = migrated_engine.connect()
    outer = connection.begin()
    for table in LOCKED_TABLES:
        connection.execute(text(f"LOCK TABLE {table} IN SHARE UPDATE EXCLUSIVE MODE"))
    world = insert_perf_data(connection, FROZEN_NOW, DEFAULT_TICKETS, DEFAULT_EVENTS)
    for statement in KPI_DATA:
        connection.execute(text(statement))
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


def p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, int(len(ordered) * 0.95) - 1)]


def test_kpi_data_volume(db: Session) -> None:
    acknowledged = db.scalar(
        text("SELECT count(*) FROM ticket_events WHERE action = 'acknowledged'")
    )
    escalations = db.scalar(text("SELECT count(*) FROM escalation_events"))
    assert db.scalar(text("SELECT count(*) FROM tickets")) == DEFAULT_TICKETS
    assert isinstance(acknowledged, int)
    assert acknowledged > DEFAULT_TICKETS // 2
    assert isinstance(escalations, int)
    assert escalations > 0


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_kpi_p95_under_budget(
    case: Case,
    client: TestClient,
    perf_connection: tuple[Connection, PerfWorld],
    clock: FrozenClock,
    settings: Settings,
) -> None:
    _, world = perf_connection
    actors: dict[str, uuid.UUID] = {"admin": world.admin_id, "spoke": world.spoke_id}
    token = create_access_token(actors[case.actor], clock.now(), settings).token
    headers = {"Authorization": f"Bearer {token}"}
    samples: list[float] = []
    for attempt in range(WARMUP + RUNS):
        started = time.perf_counter()
        response = client.get(case.path, params=dict(case.params), headers=headers)
        elapsed = (time.perf_counter() - started) * 1000
        assert response.status_code == 200, response.text
        if attempt >= WARMUP:
            samples.append(elapsed)
    assert p95(samples) < P95_BUDGET_MS, f"{case.name}: p95 {p95(samples):.1f} ms"
