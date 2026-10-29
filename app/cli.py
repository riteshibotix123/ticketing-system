import argparse
import getpass
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TextIO

from alembic import command
from alembic.config import Config
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.clock import Clock, SystemClock
from app.core.config import Environment, Settings, get_settings
from app.core.db import SessionLocal, database_url
from app.core.enums import AccountState, Role
from app.core.security import hash_password, password_policy_error
from app.main import create_app
from app.models.identity import User
from app.models.org import Department
from app.schemas.auth import NormalizedEmail
from app.schemas.org import DepartmentId, OrgName
from app.schemas.signup import PersonName
from app.seed.run import SeedRefused, seed
from app.services.audit import AuditService
from app.services.mfa import MfaService

ADMIN_PASSWORD_ENV: Final = "ADMIN_PASSWORD"
DEFAULT_DEPARTMENT: Final = "ADM"
DEFAULT_DEPARTMENT_NAME: Final = "Administration & Facilities"
BACKEND_ROOT: Final = Path(__file__).resolve().parents[1]
RESETTABLE: Final = frozenset({Environment.DEV, Environment.TEST})

_email = TypeAdapter(NormalizedEmail)
_name = TypeAdapter(PersonName)
_department = TypeAdapter(DepartmentId)
_department_name = TypeAdapter(OrgName)


@dataclass(frozen=True, slots=True)
class CliContext:
    session_factory: Callable[[], Session]
    settings: Settings
    clock: Clock
    out: TextIO
    environ: Mapping[str, str]
    prompt: Callable[[str], str]


def _fail(context: CliContext, message: str) -> int:
    context.out.write(f"{message}\n")
    return 1


def _password(context: CliContext) -> str:
    value = context.environ.get(ADMIN_PASSWORD_ENV)
    if value:
        return value
    return context.prompt("Password: ")


def create_super_admin(args: argparse.Namespace, context: CliContext) -> int:
    try:
        email = _email.validate_python(args.email)
        name = _name.validate_python(args.name)
        code = _department.validate_python(args.department)
        department_name = _department_name.validate_python(args.department_name)
    except ValidationError:
        return _fail(context, "Enter a valid email, name, department code and department name")
    password = _password(context)
    policy_error = password_policy_error(password)
    if policy_error is not None:
        return _fail(context, f"Password rejected: {policy_error}")
    with context.session_factory() as session:
        if session.scalars(select(User.id).where(User.email == email)).first() is not None:
            return _fail(context, f"A user with email {email} already exists")
        now = context.clock.now()
        if session.get(Department, code) is None:
            session.add(
                Department(
                    id=code,
                    name=department_name,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
        user = User(
            email=email,
            name=name,
            password_hash=hash_password(password),
            home_department_id=code,
            global_role=Role.SUPER_ADMIN,
            state=AccountState.ACTIVE,
            email_verified_at=now,
            approved_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()
        AuditService(session, context.clock).record(
            action="super_admin_created",
            object_type="user",
            object_id=user.id,
            new_value={"email": email, "role": Role.SUPER_ADMIN},
            is_security_limited=True,
        )
        session.commit()
    context.out.write(f"Super Admin {email} created\n")
    return 0


def seed_data(_args: argparse.Namespace, context: CliContext) -> int:
    with context.session_factory() as session:
        try:
            result = seed(session, context.settings, context.clock)
        except SeedRefused as exc:
            return _fail(context, str(exc))
        session.commit()
    if not result.created:
        context.out.write("Seed data already present, nothing changed\n")
        return 0
    context.out.write(f"Seeded {result.users} users and {result.tickets} tickets\n")
    return 0


def reset_db(_args: argparse.Namespace, context: CliContext) -> int:
    if context.settings.env not in RESETTABLE:
        return _fail(context, "reset-db is only allowed when ENV is dev or test")
    url = database_url(context.settings)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    alembic_config.attributes["url"] = url
    command.upgrade(alembic_config, "head")
    context.out.write("Database schema recreated\n")
    return 0


def export_openapi(args: argparse.Namespace, context: CliContext) -> int:
    schema = create_app(context.settings).openapi()
    target = Path(args.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    context.out.write(f"OpenAPI schema written to {target}\n")
    return 0


def mfa_reset(args: argparse.Namespace, context: CliContext) -> int:
    with context.session_factory() as session:
        found = MfaService(session, context.clock, context.settings).reset(args.email)
        if not found:
            return _fail(context, f"No user with email {args.email}")
        session.commit()
    context.out.write(f"MFA cleared for {args.email}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    bootstrap = commands.add_parser("create-super-admin", help="create an active Super Admin")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--name", required=True)
    bootstrap.add_argument("--department", default=DEFAULT_DEPARTMENT)
    bootstrap.add_argument("--department-name", default=DEFAULT_DEPARTMENT_NAME)
    bootstrap.set_defaults(handler=create_super_admin)

    seeding = commands.add_parser("seed", help="load the demo data (not in prod)")
    seeding.set_defaults(handler=seed_data)

    reset = commands.add_parser("reset-db", help="recreate the schema (dev and test only)")
    reset.set_defaults(handler=reset_db)

    openapi = commands.add_parser("export-openapi", help="write the OpenAPI JSON")
    openapi.add_argument("path")
    openapi.set_defaults(handler=export_openapi)

    mfa = commands.add_parser("mfa-reset", help="clear a user's MFA enrolment")
    mfa.add_argument("--email", required=True)
    mfa.set_defaults(handler=mfa_reset)
    return parser


def run(argv: Sequence[str], context: CliContext) -> int:
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace, CliContext], int] = args.handler
    return handler(args, context)


def main(argv: Sequence[str] | None = None) -> int:
    context = CliContext(
        session_factory=SessionLocal,
        settings=get_settings(),
        clock=SystemClock(),
        out=sys.stdout,
        environ=os.environ,
        prompt=getpass.getpass,
    )
    return run(sys.argv[1:] if argv is None else argv, context)


if __name__ == "__main__":
    sys.exit(main())
