import io
import json
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import CliContext, run
from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.enums import AccountState, Role
from app.core.security import verify_password
from app.models import AuditLog, Department, MfaRecoveryCode, Ticket, User
from tests.factories import make_department, make_user

ADMIN_PASSWORD = "Bootstrap-Secret-42"
PROD = Settings(env=Environment.PROD, jwt_secret=SecretStr("p" * 40), cookie_secure=True)


def no_prompt(_label: str) -> str:
    raise AssertionError("prompt should not be used")


def context_for(
    db: Session,
    settings: Settings,
    clock: FrozenClock,
    environ: Mapping[str, str] | None = None,
    prompt: Callable[[str], str] = no_prompt,
) -> CliContext:
    def factory() -> Session:
        return Session(
            bind=db.connection(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        )

    return CliContext(
        session_factory=factory,
        settings=settings,
        clock=clock,
        out=io.StringIO(),
        environ=environ if environ is not None else {"ADMIN_PASSWORD": ADMIN_PASSWORD},
        prompt=prompt,
    )


def output(context: CliContext) -> str:
    stream = context.out
    assert isinstance(stream, io.StringIO)
    return stream.getvalue()


def test_create_super_admin_bootstraps_an_active_account(db: Session, clock: FrozenClock) -> None:
    context = context_for(db, PROD, clock)
    code = run(
        ["create-super-admin", "--email", " Root@Ibotix.ai ", "--name", "Root Admin"], context
    )
    assert code == 0
    user = db.scalars(select(User).where(User.email == "root@ibotix.ai")).one()
    assert user.global_role is Role.SUPER_ADMIN
    assert user.state is AccountState.ACTIVE
    assert user.home_department_id == "ADM"
    assert verify_password(user.password_hash, ADMIN_PASSWORD)
    assert db.get(Department, "ADM") is not None
    assert "super_admin_created" in set(db.scalars(select(AuditLog.action)))

    again = context_for(db, PROD, clock)
    assert run(["create-super-admin", "--email", "root@ibotix.ai", "--name", "Other"], again) == 1
    assert "already exists" in output(again)


def test_create_super_admin_uses_prompt_and_password_policy(
    db: Session, settings: Settings, clock: FrozenClock
) -> None:
    make_department(db, "IT")
    prompts: list[str] = []

    def prompt(label: str) -> str:
        prompts.append(label)
        return "too-weak"

    context = context_for(db, settings, clock, environ={}, prompt=prompt)
    args = ["create-super-admin", "--email", "a@ibotix.ai", "--name", "Al", "--department", "IT"]
    assert run(args, context) == 1
    assert prompts == ["Password: "]
    assert "Password rejected" in output(context)
    assert db.scalar(select(func.count()).select_from(User)) == 0

    invalid = context_for(db, settings, clock)
    bad = ["create-super-admin", "--email", "nope", "--name", "Al"]
    assert run(bad, invalid) == 1


def test_seed_command_is_idempotent(db: Session, settings: Settings, clock: FrozenClock) -> None:
    first = context_for(db, settings, clock)
    assert run(["seed"], first) == 0
    assert output(first).startswith("Seeded ")
    tickets = db.scalar(select(func.count()).select_from(Ticket))
    second = context_for(db, settings, clock)
    assert run(["seed"], second) == 0
    assert "already present" in output(second)
    assert db.scalar(select(func.count()).select_from(Ticket)) == tickets


def test_seed_and_reset_refuse_in_prod(db: Session, clock: FrozenClock) -> None:
    seeding = context_for(db, PROD, clock)
    assert run(["seed"], seeding) == 1
    assert "ENV=prod" in output(seeding)
    assert db.scalar(select(func.count()).select_from(Department)) == 0
    reset = context_for(db, PROD, clock)
    assert run(["reset-db"], reset) == 1
    assert "dev or test" in output(reset)


def test_export_openapi_writes_the_schema(
    db: Session, settings: Settings, clock: FrozenClock, tmp_path: Path
) -> None:
    target = tmp_path / "out" / "openapi.json"
    context = context_for(db, settings, clock)
    assert run(["export-openapi", str(target)], context) == 0
    schema = json.loads(target.read_text(encoding="utf-8"))
    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/auth/mfa/verify" in schema["paths"]


def test_mfa_reset_clears_enrolment(db: Session, settings: Settings, clock: FrozenClock) -> None:
    department = make_department(db, "IT")
    user = make_user(db, department, email="ops@ibotix.ai", role=Role.ADMIN)
    user.mfa_enabled = True
    user.mfa_secret_encrypted = "encrypted"
    db.add(
        MfaRecoveryCode(
            user_id=user.id, code_hash="x", created_at=clock.now(), updated_at=clock.now()
        )
    )
    db.flush()

    context = context_for(db, settings, clock)
    assert run(["mfa-reset", "--email", "ops@ibotix.ai"], context) == 0
    db.refresh(user)
    assert not user.mfa_enabled
    assert user.mfa_secret_encrypted is None
    assert db.scalars(select(MfaRecoveryCode.used_at)).one() == clock.now()
    assert "mfa_reset" in set(db.scalars(select(AuditLog.action)))

    missing = context_for(db, settings, clock)
    assert run(["mfa-reset", "--email", "nobody@ibotix.ai"], missing) == 1


def test_unknown_command_exits_with_usage(
    db: Session, settings: Settings, clock: FrozenClock
) -> None:
    with pytest.raises(SystemExit):
        run(["explode"], context_for(db, settings, clock))
