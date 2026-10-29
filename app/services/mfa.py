import math
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import jwt
import pyotp
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.enums import AccountState
from app.core.errors import (
    ApiError,
    conflict,
    not_found,
    too_many_attempts,
    unauthenticated,
    validation_error,
)
from app.core.security import JWT_ALGORITHM, hash_token
from app.models.identity import MfaRecoveryCode, User
from app.policy import Actor
from app.schemas.auth import MfaEnrolRequired, MfaRequired, MfaSetupResponse
from app.services.audit import AuditService

MFA_PURPOSE: Final = "mfa"
MFA_TOKEN_LIFETIME: Final = timedelta(minutes=5)
MFA_TOKEN_CLAIMS: Final = ("sub", "aud", "purpose", "iat", "exp")
MFA_ISSUER: Final = "Ibotix Helpdesk"
MAX_FAILED_MFA: Final = 5
MFA_LOCKOUT: Final = timedelta(minutes=15)
TOTP_WINDOW: Final = 1
TOTP_DIGITS: Final = 6
RECOVERY_CODE_COUNT: Final = 8
INVALID_CODE: Final = "Invalid code"

type MfaChallenge = MfaRequired | MfaEnrolRequired


@dataclass(frozen=True, slots=True)
class EnrolledUser:
    user: User
    recovery_codes: list[str]


def create_mfa_token(user_id: uuid.UUID, now: datetime, settings: Settings) -> str:
    issued_at = int(now.timestamp())
    claims = {
        "sub": str(user_id),
        "aud": MFA_PURPOSE,
        "purpose": MFA_PURPOSE,
        "iat": issued_at,
        "exp": issued_at + int(MFA_TOKEN_LIFETIME.total_seconds()),
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_mfa_token(token: str, now: datetime, settings: Settings) -> uuid.UUID | None:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            audience=MFA_PURPOSE,
            options={
                "require": list(MFA_TOKEN_CLAIMS),
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
    except jwt.InvalidTokenError:
        return None
    expires_at = claims.get("exp")
    subject = claims.get("sub")
    if claims.get("purpose") != MFA_PURPOSE:
        return None
    if not isinstance(expires_at, int) or not isinstance(subject, str):
        return None
    if expires_at <= now.timestamp():
        return None
    try:
        return uuid.UUID(subject)
    except ValueError:
        return None


def mfa_required_for(actor: Actor, settings: Settings) -> bool:
    required = set(settings.mfa_required_roles)
    return any(role.value in required for role in actor.roles)


def _new_recovery_code() -> str:
    return f"{secrets.token_hex(4)}-{secrets.token_hex(4)}"


def _normalize(code: str) -> str:
    return "".join(code.split()).lower()


class MfaService:
    def __init__(self, session: Session, clock: Clock, settings: Settings) -> None:
        self._session = session
        self._clock = clock
        self._settings = settings
        self._audit = AuditService(session, clock)

    def challenge(self, user: User, actor: Actor) -> MfaChallenge | None:
        if not self._settings.mfa_enabled:
            return None
        now = self._clock.now()
        if user.mfa_enabled:
            return MfaRequired(mfa_token=create_mfa_token(user.id, now, self._settings))
        if mfa_required_for(actor, self._settings):
            return MfaEnrolRequired(mfa_token=create_mfa_token(user.id, now, self._settings))
        return None

    def setup(self, token: str) -> MfaSetupResponse:
        user = self._token_user(token)
        if user.mfa_enabled:
            raise conflict("MFA is already enabled")
        secret = pyotp.random_base32()
        user.mfa_secret_encrypted = self._fernet().encrypt(secret.encode()).decode()
        user.updated_at = self._clock.now()
        self._session.flush()
        uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=MFA_ISSUER)
        return MfaSetupResponse(secret=secret, otpauth_uri=uri)

    def confirm(self, token: str, code: str) -> EnrolledUser:
        user = self._token_user(token)
        if user.mfa_enabled or user.mfa_secret_encrypted is None:
            raise conflict("MFA setup has not been started")
        now = self._clock.now()
        if not self._totp_matches(user, code, now):
            raise validation_error({"code": INVALID_CODE})
        self._retire_recovery_codes(user, now)
        codes = [_new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        self._session.add_all(
            MfaRecoveryCode(
                user_id=user.id, code_hash=hash_token(raw), created_at=now, updated_at=now
            )
            for raw in codes
        )
        user.mfa_enabled = True
        user.mfa_failed_count = 0
        user.updated_at = now
        self._audit.record(
            action="mfa_enabled", object_type="user", object_id=user.id, actor_id=user.id
        )
        self._session.flush()
        return EnrolledUser(user=user, recovery_codes=codes)

    def verify(self, token: str, code: str) -> User | ApiError:
        user = self._token_user(token)
        if not user.mfa_enabled:
            raise conflict("MFA is not enabled")
        now = self._clock.now()
        if user.locked_until is not None and user.locked_until > now:
            return too_many_attempts(_retry_after(user.locked_until, now))
        if self._totp_matches(user, code, now) or self._use_recovery_code(user, code, now):
            user.mfa_failed_count = 0
            user.updated_at = now
            return user
        return self._register_failure(user, now)

    def reset(self, email: str) -> bool:
        user = self._session.scalars(
            select(User).where(User.email == email.strip().lower()).with_for_update()
        ).first()
        if user is None:
            return False
        now = self._clock.now()
        self._retire_recovery_codes(user, now)
        user.mfa_enabled = False
        user.mfa_secret_encrypted = None
        user.mfa_failed_count = 0
        user.updated_at = now
        self._audit.record(action="mfa_reset", object_type="user", object_id=user.id)
        self._session.flush()
        return True

    def _token_user(self, token: str) -> User:
        if not self._settings.mfa_enabled:
            raise not_found()
        user_id = decode_mfa_token(token, self._clock.now(), self._settings)
        if user_id is None:
            raise unauthenticated()
        user = self._session.get(User, user_id, with_for_update=True)
        if user is None or user.state is not AccountState.ACTIVE:
            raise unauthenticated()
        return user

    def _fernet(self) -> Fernet:
        key = self._settings.field_encryption_key.get_secret_value()
        if not key:
            raise RuntimeError("FIELD_ENCRYPTION_KEY is required when MFA is used")
        return Fernet(key.encode())

    def _totp_matches(self, user: User, code: str, now: datetime) -> bool:
        candidate = _normalize(code)
        if user.mfa_secret_encrypted is None or len(candidate) != TOTP_DIGITS:
            return False
        if not candidate.isdigit():
            return False
        secret = self._fernet().decrypt(user.mfa_secret_encrypted.encode()).decode()
        return pyotp.TOTP(secret).verify(candidate, for_time=now, valid_window=TOTP_WINDOW)

    def _use_recovery_code(self, user: User, code: str, now: datetime) -> bool:
        recovery = self._session.scalars(
            select(MfaRecoveryCode)
            .where(
                MfaRecoveryCode.user_id == user.id,
                MfaRecoveryCode.code_hash == hash_token(_normalize(code)),
                MfaRecoveryCode.used_at.is_(None),
            )
            .with_for_update()
        ).first()
        if recovery is None:
            return False
        recovery.used_at = now
        recovery.updated_at = now
        self._audit.record(
            action="mfa_recovery_code_used", object_type="user", object_id=user.id, actor_id=user.id
        )
        return True

    def _register_failure(self, user: User, now: datetime) -> ApiError:
        user.mfa_failed_count += 1
        user.updated_at = now
        self._audit.record(
            action="mfa_failed", object_type="user", object_id=user.id, actor_id=user.id
        )
        if user.mfa_failed_count < MAX_FAILED_MFA:
            self._session.flush()
            return validation_error({"code": INVALID_CODE})
        user.mfa_failed_count = 0
        user.locked_until = now + MFA_LOCKOUT
        self._audit.record(
            action="account_locked",
            object_type="user",
            object_id=user.id,
            actor_id=user.id,
            new_value={"locked_until": user.locked_until},
        )
        self._session.flush()
        return too_many_attempts(_retry_after(user.locked_until, now))

    def _retire_recovery_codes(self, user: User, now: datetime) -> None:
        self._session.execute(
            update(MfaRecoveryCode)
            .where(MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None))
            .values(used_at=now, updated_at=now)
        )


def _retry_after(until: datetime, now: datetime) -> int:
    return max(1, math.ceil((until - now).total_seconds()))
