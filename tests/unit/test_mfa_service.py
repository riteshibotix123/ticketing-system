import uuid
from datetime import timedelta

import pyotp
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Environment, MfaRole, Settings
from app.core.enums import Role
from app.core.errors import ApiError, ErrorCode
from app.core.security import InvalidAccessToken, create_access_token, decode_access_token
from app.models import AuditLog, MfaRecoveryCode
from app.policy import Actor
from app.schemas.auth import MfaEnrolRequired, MfaRequired
from app.services.mfa import (
    MfaService,
    create_mfa_token,
    decode_mfa_token,
    mfa_required_for,
)
from tests.factories import FACTORY_NOW, make_department, make_user

KEY = Fernet.generate_key().decode()


def settings_for(*roles: MfaRole) -> Settings:
    return Settings(
        env=Environment.TEST, mfa_required_roles=list(roles), field_encryption_key=SecretStr(KEY)
    )


def actor(role: Role, spoke_departments: frozenset[str] = frozenset()) -> Actor:
    return Actor(
        id=uuid.uuid4(),
        global_role=role,
        department_id="IT",
        spoke_department_ids=spoke_departments,
        name="Someone",
        email="someone@ibotix.ai",
    )


def test_mfa_token_round_trip_and_expiry() -> None:
    settings = settings_for("admin")
    user_id = uuid.uuid4()
    token = create_mfa_token(user_id, FACTORY_NOW, settings)
    assert decode_mfa_token(token, FACTORY_NOW + timedelta(minutes=4), settings) == user_id
    assert decode_mfa_token(token, FACTORY_NOW + timedelta(minutes=5), settings) is None
    other = Settings(env=Environment.TEST, jwt_secret=SecretStr("another-secret"))
    assert decode_mfa_token(token, FACTORY_NOW, other) is None
    assert decode_mfa_token("not-a-token", FACTORY_NOW, settings) is None


def test_mfa_and_access_tokens_are_not_interchangeable() -> None:
    settings = settings_for("admin")
    user_id = uuid.uuid4()
    mfa_token = create_mfa_token(user_id, FACTORY_NOW, settings)
    with pytest.raises(InvalidAccessToken):
        decode_access_token(mfa_token, FACTORY_NOW, settings)
    access = create_access_token(user_id, FACTORY_NOW, settings).token
    assert decode_mfa_token(access, FACTORY_NOW, settings) is None


def test_required_roles_include_spoke_mapping() -> None:
    spoke_only = settings_for("spoke")
    assert mfa_required_for(actor(Role.EMPLOYEE, frozenset({"IT"})), spoke_only)
    assert not mfa_required_for(actor(Role.EMPLOYEE), spoke_only)
    assert not mfa_required_for(actor(Role.ADMIN), spoke_only)
    staff = settings_for("admin", "super_admin")
    assert mfa_required_for(actor(Role.ADMIN), staff)
    assert mfa_required_for(actor(Role.SUPER_ADMIN), staff)
    assert not mfa_required_for(actor(Role.EMPLOYEE, frozenset({"IT"})), staff)
    assert not mfa_required_for(actor(Role.SUPER_ADMIN), Settings(env=Environment.TEST))


def test_challenge_depends_on_configuration_and_enrolment(db: Session) -> None:
    department = make_department(db, "IT")
    user = make_user(db, department, role=Role.ADMIN)
    clock = FrozenClock(FACTORY_NOW)
    admin = actor(Role.ADMIN)
    assert MfaService(db, clock, Settings(env=Environment.TEST)).challenge(user, admin) is None
    enforced = MfaService(db, clock, settings_for("admin"))
    assert isinstance(enforced.challenge(user, admin), MfaEnrolRequired)
    user.mfa_enabled = True
    assert isinstance(enforced.challenge(user, admin), MfaRequired)
    spoke_only = MfaService(db, clock, settings_for("spoke"))
    assert isinstance(spoke_only.challenge(user, admin), MfaRequired)
    assert MfaService(db, clock, Settings(env=Environment.TEST)).challenge(user, admin) is None


def test_setup_confirm_verify_and_reset(db: Session) -> None:
    department = make_department(db, "IT")
    user = make_user(db, department, email="ops@ibotix.ai", role=Role.ADMIN)
    clock = FrozenClock(FACTORY_NOW)
    service = MfaService(db, clock, settings_for("admin"))
    token = create_mfa_token(user.id, clock.now(), settings_for("admin"))

    setup = service.setup(token)
    assert user.mfa_secret_encrypted is not None
    assert setup.secret not in user.mfa_secret_encrypted
    assert "ops%40ibotix.ai" in setup.otpauth_uri
    enrolled = service.confirm(token, pyotp.TOTP(setup.secret).at(clock.now()))
    assert user.mfa_enabled
    assert len(enrolled.recovery_codes) == 8

    assert service.verify(token, pyotp.TOTP(setup.secret).at(clock.now())) is user
    failure = service.verify(token, "123")
    assert isinstance(failure, ApiError)
    assert failure.code is ErrorCode.VALIDATION_ERROR
    assert user.mfa_failed_count == 1

    assert service.reset("OPS@ibotix.ai")
    assert not user.mfa_enabled
    assert user.mfa_secret_encrypted is None
    assert user.mfa_failed_count == 0
    unused = db.scalars(select(MfaRecoveryCode).where(MfaRecoveryCode.used_at.is_(None)))
    assert list(unused) == []
    assert "mfa_reset" in set(db.scalars(select(AuditLog.action)))
    assert not service.reset("nobody@ibotix.ai")


def test_service_endpoints_are_hidden_when_disabled(db: Session) -> None:
    department = make_department(db, "IT")
    user = make_user(db, department, role=Role.ADMIN)
    clock = FrozenClock(FACTORY_NOW)
    token = create_mfa_token(user.id, clock.now(), settings_for("admin"))
    disabled = MfaService(db, clock, Settings(env=Environment.TEST))
    with pytest.raises(ApiError) as raised:
        disabled.setup(token)
    assert raised.value.code is ErrorCode.NOT_FOUND


def test_missing_encryption_key_fails_loudly(db: Session) -> None:
    department = make_department(db, "IT")
    user = make_user(db, department, role=Role.ADMIN)
    clock = FrozenClock(FACTORY_NOW)
    settings = Settings(env=Environment.TEST, mfa_required_roles=["admin"])
    token = create_mfa_token(user.id, clock.now(), settings)
    with pytest.raises(RuntimeError):
        MfaService(db, clock, settings).setup(token)
