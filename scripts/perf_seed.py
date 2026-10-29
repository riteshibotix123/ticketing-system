import argparse
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import Connection, create_engine, text

from app.core.clock import SystemClock
from app.core.config import Environment, get_settings
from app.core.db import database_url

DEPARTMENTS: Final = ("IT", "ENG", "HR", "ADM", "FIN", "SEC", "SAL", "OPS", "LEG")
STATUSES: Final = (
    "new",
    "acknowledged",
    "assigned",
    "in_progress",
    "awaiting_requester",
    "on_hold",
    "resolved",
    "closed",
    "reopened",
    "cancelled",
)
PRIORITIES: Final = ("low", "medium", "high", "critical")
TOPICS: Final = ("printer", "vpn", "laptop", "payroll", "invoice", "access", "contract", "badge")
EMPLOYEES: Final = 450
DEFAULT_TICKETS: Final = 50_000
DEFAULT_EVENTS: Final = 200_000
PASSWORD_PLACEHOLDER: Final = "perf-seed-no-login"


@dataclass(frozen=True, slots=True)
class PerfWorld:
    admin_id: uuid.UUID
    spoke_id: uuid.UUID
    spoke_department: str
    employee_id: uuid.UUID
    topic: str


STATEMENTS: Final = (
    """
    INSERT INTO departments (id, name, is_active, created_at, updated_at)
    SELECT code, code || ' Department', true, :now, :now FROM unnest(CAST(:codes AS text[])) AS code
    ON CONFLICT (id) DO NOTHING
    """,
    """
    INSERT INTO users (id, email, name, password_hash, home_department_id, global_role, state,
                       email_verified_at, approved_at, failed_login_count, mfa_enabled,
                       mfa_failed_count, created_at, updated_at)
    SELECT gen_random_uuid(), 'perf-user-' || n || '@ibotix.ai', 'Perf User ' || n, :password,
           (CAST(:codes AS text[]))[1 + n % 9], 'employee', 'active', :now, :now, 0, false, 0,
           :now, :now
    FROM generate_series(0, :employees - 1) AS n
    """,
    """
    INSERT INTO users (id, email, name, password_hash, home_department_id, global_role, state,
                       email_verified_at, approved_at, failed_login_count, mfa_enabled,
                       mfa_failed_count, created_at, updated_at)
    SELECT gen_random_uuid(), 'perf-spoke-' || lower(code) || '@ibotix.ai', 'Perf Spoke ' || code,
           :password, code, 'employee', 'active', :now, :now, 0, false, 0, :now, :now
    FROM unnest(CAST(:codes AS text[])) AS code
    UNION ALL
    SELECT gen_random_uuid(), 'perf-admin@ibotix.ai', 'Perf Admin', :password, 'ADM', 'admin',
           'active', :now, :now, 0, false, 0, :now, :now
    """,
    """
    INSERT INTO spoke_assignments (id, user_id, department_id, granted_at)
    SELECT gen_random_uuid(), id, home_department_id, :now
    FROM users WHERE email LIKE 'perf-spoke-%'
    """,
    """
    INSERT INTO categories (id, department_id, name, is_confidential, is_active,
                            created_at, updated_at)
    SELECT gen_random_uuid(), code, 'Perf category ' || slot, slot = 2, true, :now, :now
    FROM unnest(CAST(:codes AS text[])) AS code, generate_series(0, 2) AS slot
    """,
    """
    WITH requesters AS (
        SELECT id, row_number() OVER (ORDER BY email) - 1 AS idx
        FROM users WHERE email LIKE 'perf-user-%'
    ),
    cats AS (
        SELECT id, department_id, is_confidential,
               row_number() OVER (PARTITION BY department_id ORDER BY name) - 1 AS idx
        FROM categories WHERE name LIKE 'Perf category %'
    ),
    numbers AS (
        SELECT n, (CAST(:codes AS text[]))[1 + n % 9] AS code,
               (CAST(:statuses AS text[]))[1 + (n / 9) % 10] AS status,
               (CAST(:priorities AS text[]))[1 + n % 4] AS priority,
               CASE WHEN n % 20 = 0 THEN 2 ELSE n % 2 END AS cat_idx,
               :now - make_interval(hours => n % 2000) AS at
        FROM generate_series(1, :tickets) AS n
    )
    INSERT INTO tickets (id, ticket_no, origin_department_code, department_id, category_id, title,
                         description, requested_priority, priority, confidential, status,
                         requester_id, assignee_id, sla_started_at, reopen_count,
                         escalation_level, update_overdue, created_at, updated_at)
    SELECT gen_random_uuid(), 'IBX-' || numbers.code || '-2026-' || lpad(n::text, 6, '0'),
           numbers.code, numbers.code, cats.id,
           'Perf ticket ' || n || ' ' || (CAST(:topics AS text[]))[1 + n % 8],
           'Generated ticket ' || n || ' for performance tests',
           numbers.priority, numbers.priority, cats.is_confidential, numbers.status,
           requesters.id,
           CASE WHEN n % 5 = 0 THEN requesters.id END,
           numbers.at, 0,
           CASE WHEN numbers.status IN ('resolved', 'closed', 'cancelled') THEN 0 ELSE n % 4 END,
           n % 7 = 0, numbers.at, numbers.at
    FROM numbers
    JOIN requesters ON requesters.idx = (n * 7) % :employees
    JOIN cats ON cats.department_id = numbers.code AND cats.idx = numbers.cat_idx
    """,
    """
    WITH perf_tickets AS (
        SELECT id, created_at, row_number() OVER (ORDER BY ticket_no) - 1 AS idx
        FROM tickets WHERE title LIKE 'Perf ticket %'
    )
    INSERT INTO ticket_events (id, ticket_id, at, kind, action, body, is_public)
    SELECT gen_random_uuid(), perf_tickets.id,
           perf_tickets.created_at + make_interval(mins => e % 600),
           CASE WHEN e % 3 = 0 THEN 'comment' ELSE 'audit' END,
           CASE WHEN e % 3 = 0 THEN NULL ELSE 'status_changed' END,
           CASE WHEN e % 3 = 0 THEN 'Generated comment ' || e END,
           e % 4 <> 0
    FROM generate_series(1, :events) AS e
    JOIN perf_tickets ON perf_tickets.idx = e % :tickets
    """,
)

ANALYZE_AFTER: Final = (
    ("departments",),
    (),
    ("users",),
    ("spoke_assignments",),
    ("categories",),
    ("tickets",),
    ("ticket_events",),
)


def insert_perf_data(
    connection: Connection,
    now: datetime,
    tickets: int = DEFAULT_TICKETS,
    events: int = DEFAULT_EVENTS,
) -> PerfWorld:
    params = {
        "now": now,
        "codes": list(DEPARTMENTS),
        "statuses": list(STATUSES),
        "priorities": list(PRIORITIES),
        "topics": list(TOPICS),
        "password": PASSWORD_PLACEHOLDER,
        "employees": EMPLOYEES,
        "tickets": tickets,
        "events": events,
    }
    for statement, analyze in zip(STATEMENTS, ANALYZE_AFTER, strict=True):
        connection.execute(text(statement), params)
        for table in analyze:
            connection.execute(text(f"ANALYZE {table}"))
    return _world(connection)


def _world(connection: Connection) -> PerfWorld:
    def user_id(email: str) -> uuid.UUID:
        value = connection.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        ).scalar_one()
        if not isinstance(value, uuid.UUID):
            raise TypeError("user id is not a UUID")
        return value

    return PerfWorld(
        admin_id=user_id("perf-admin@ibotix.ai"),
        spoke_id=user_id("perf-spoke-it@ibotix.ai"),
        spoke_department="IT",
        employee_id=user_id("perf-user-7@ibotix.ai"),
        topic=TOPICS[3],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Insert synthetic tickets for performance tests")
    parser.add_argument("--tickets", type=int, default=DEFAULT_TICKETS)
    parser.add_argument("--events", type=int, default=DEFAULT_EVENTS)
    args = parser.parse_args()
    settings = get_settings()
    if settings.env is Environment.PROD:
        sys.stdout.write("perf_seed.py refuses to run when ENV=prod\n")
        return 1
    engine = create_engine(database_url(settings))
    try:
        with engine.begin() as connection:
            insert_perf_data(connection, SystemClock().now(), args.tickets, args.events)
    finally:
        engine.dispose()
    sys.stdout.write(f"Inserted {args.tickets} tickets and {args.events} events\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
