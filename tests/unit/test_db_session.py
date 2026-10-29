from collections.abc import Generator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session

from app.core.db import transactional
from app.core.enums import (
    PRIORITY_RANK,
    AccountState,
    Priority,
    ProtectedActionKind,
    ProtectedActionStatus,
    Role,
    ScanStatus,
    SignupStatus,
    SlaKind,
    TicketAction,
    TicketStatus,
)
from app.core.ids import format_ticket_no


@pytest.fixture
def probe(db: Session) -> Connection:
    bind = db.get_bind()
    assert isinstance(bind, Connection)
    bind.execute(text("CREATE TEMP TABLE probe (value integer NOT NULL)"))
    return bind


def _count(connection: Connection) -> int:
    count: int = connection.execute(text("SELECT count(*) FROM probe")).scalar_one()
    return count


def test_transactional_commits_on_success(db: Session, probe: Connection) -> None:
    scope: Generator[Session] = transactional(db)
    session = next(scope)
    session.execute(text("INSERT INTO probe (value) VALUES (1)"))
    with pytest.raises(StopIteration):
        next(scope)
    assert _count(probe) == 1


def test_transactional_rolls_back_on_error(db: Session, probe: Connection) -> None:
    scope: Generator[Session] = transactional(db)
    session = next(scope)
    session.execute(text("INSERT INTO probe (value) VALUES (1)"))
    with pytest.raises(RuntimeError, match="boom"):
        scope.throw(RuntimeError("boom"))
    assert _count(probe) == 0


def test_rolled_back_work_does_not_affect_earlier_commit(db: Session, probe: Connection) -> None:
    first: Generator[Session] = transactional(db)
    next(first).execute(text("INSERT INTO probe (value) VALUES (1)"))
    with pytest.raises(StopIteration):
        next(first)
    second: Generator[Session] = transactional(db)
    next(second).execute(text("INSERT INTO probe (value) VALUES (2)"))
    with pytest.raises(RuntimeError):
        second.throw(RuntimeError("boom"))
    assert _count(probe) == 1


def test_database_is_postgresql_with_pg_trgm(db: Session) -> None:
    assert db.get_bind().dialect.name == "postgresql"
    installed = db.execute(
        text("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'")
    ).scalar_one()
    assert installed == 1


def test_committed_db_really_commits(committed_db: Session, migrated_engine: Engine) -> None:
    committed_db.execute(text("CREATE TABLE IF NOT EXISTS commit_probe (value integer)"))
    committed_db.execute(text("INSERT INTO commit_probe (value) VALUES (7)"))
    committed_db.commit()
    try:
        with migrated_engine.connect() as other:
            seen = other.execute(text("SELECT value FROM commit_probe")).scalar_one()
        assert seen == 7
    finally:
        with migrated_engine.begin() as connection:
            connection.execute(text("DROP TABLE commit_probe"))


def test_enums_match_contract() -> None:
    assert [m.value for m in Role] == ["super_admin", "admin", "spoke", "employee"]
    assert [m.value for m in AccountState] == [
        "pending_verification",
        "pending_approval",
        "active",
        "rejected",
        "deactivated",
    ]
    assert [m.value for m in Priority] == ["low", "medium", "high", "critical"]
    assert [m.value for m in TicketStatus] == [
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
    ]
    assert [m.value for m in TicketAction] == [
        "acknowledge",
        "assign",
        "transfer",
        "change_priority",
        "revise_eta",
        "start_work",
        "ask_requester",
        "hold",
        "resume",
        "resolve",
        "confirm_closure",
        "reopen",
        "cancel",
        "close_admin",
        "comment",
        "internal_note",
        "manage_collaborators",
    ]
    assert [m.value for m in SlaKind] == ["initial_response", "progress_update", "eta"]
    assert [m.value for m in ScanStatus] == ["pending", "clean", "infected"]
    assert [m.value for m in ProtectedActionKind] == [
        "deactivate_super_admin",
        "demote_super_admin",
    ]
    assert [m.value for m in ProtectedActionStatus] == [
        "pending",
        "approved",
        "rejected",
        "expired",
    ]
    assert [m.value for m in SignupStatus] == ["pending", "approved", "rejected"]


def test_priority_rank() -> None:
    assert dict(PRIORITY_RANK) == {
        Priority.LOW: 1,
        Priority.MEDIUM: 2,
        Priority.HIGH: 3,
        Priority.CRITICAL: 4,
    }


def test_format_ticket_no() -> None:
    assert format_ticket_no("IT", 2026, 1234) == "IBX-IT-2026-001234"
    assert format_ticket_no("FINOPS", 2027, 999999) == "IBX-FINOPS-2027-999999"


@pytest.mark.parametrize(
    ("code", "year", "seq"),
    [("it", 2026, 1), ("I", 2026, 1), ("TOOLONG", 2026, 1), ("IT", 26, 1), ("IT", 2026, 0)],
)
def test_format_ticket_no_rejects_invalid(code: str, year: int, seq: int) -> None:
    with pytest.raises(ValueError, match="must"):
        format_ticket_no(code, year, seq)
