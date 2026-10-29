import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.enums import AccountState, SignupStatus
from app.core.errors import (
    ApiError,
    account_state,
    invalid_credentials,
    rate_limited,
    token_expired,
    too_many_attempts,
    unauthenticated,
    validation_error,
)
from app.core.request_context import get_request_context
from app.core.security import (
    create_access_token,
    dummy_verify,
    hash_password,
    hash_token,
    new_opaque_token,
    password_policy_error,
    verify_password,
)
from app.models.identity import EmailToken, EmailTokenPurpose, RefreshToken, SignupRequest, User
from app.policy import Actor
from app.schemas.auth import LoginSuccess, MfaConfirmSuccess, MfaSetupResponse, RefreshResponse
from app.services.audit import AuditService
from app.services.email_outbox import enqueue_email
from app.services.me import MeService
from app.services.mfa import MfaChallenge, MfaService
from app.services.rate_limit import (
    FORGOT_PER_EMAIL,
    LOGIN_PER_EMAIL,
    LOGIN_PER_IP,
    RateLimiter,
)

MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
RESET_TOKEN_LIFETIME = timedelta(hours=1)
RESET_TEMPLATE = "password_reset"
INVALID_RESET_TOKEN = "This link is invalid or has already been used"


@dataclass(frozen=True, slots=True)
class LoginGranted:
    body: LoginSuccess
    refresh_token: str


@dataclass(frozen=True, slots=True)
class MfaEnrolGranted:
    body: MfaConfirmSuccess
    refresh_token: str


@dataclass(frozen=True, slots=True)
class RefreshGranted:
    body: RefreshResponse
    refresh_token: str


def _retry_after(until: datetime, now: datetime) -> int:
    return max(1, math.ceil((until - now).total_seconds()))


class AuthService:
    def __init__(self, session: Session, clock: Clock, settings: Settings) -> None:
        self._session = session
        self._clock = clock
        self._settings = settings
        self._audit = AuditService(session, clock)
        self._limiter = RateLimiter(session, clock)
        self._mfa = MfaService(session, clock, settings)
        self._me = MeService(session)

    def login(self, email: str, password: str) -> LoginGranted | MfaChallenge | ApiError:
        retry_after = self._login_rate_limit(email)
        if retry_after is not None:
            return rate_limited(retry_after)
        now = self._clock.now()
        user = self._session.scalars(
            select(User).where(User.email == email).with_for_update()
        ).first()
        if user is None:
            dummy_verify(password)
            self._audit.record(
                action="login_failed", object_type="user", new_value={"email": email}
            )
            return invalid_credentials()
        if user.locked_until is not None and user.locked_until > now:
            return too_many_attempts(_retry_after(user.locked_until, now))
        if not verify_password(user.password_hash, password):
            return self._register_failure(user, now)
        if user.state is not AccountState.ACTIVE:
            reason = self._rejection_reason(user) if user.state is AccountState.REJECTED else None
            return account_state(user.state.value, reason)
        user.failed_login_count = 0
        user.locked_until = None
        user.updated_at = now
        actor = self._me.actor_for(user)
        challenge = self._mfa.challenge(user, actor)
        if challenge is not None:
            self._session.flush()
            return challenge
        return self._grant(user, actor)

    def mfa_setup(self, mfa_token: str) -> MfaSetupResponse:
        return self._mfa.setup(mfa_token)

    def mfa_confirm(self, mfa_token: str, code: str) -> MfaEnrolGranted:
        enrolled = self._mfa.confirm(mfa_token, code)
        granted = self._grant(enrolled.user, self._me.actor_for(enrolled.user))
        body = MfaConfirmSuccess(
            access_token=granted.body.access_token,
            expires_in=granted.body.expires_in,
            user=granted.body.user,
            recovery_codes=enrolled.recovery_codes,
        )
        return MfaEnrolGranted(body=body, refresh_token=granted.refresh_token)

    def mfa_verify(self, mfa_token: str, code: str) -> LoginGranted | ApiError:
        result = self._mfa.verify(mfa_token, code)
        if isinstance(result, ApiError):
            return result
        return self._grant(result, self._me.actor_for(result))

    def refresh(self, raw_token: str | None) -> RefreshGranted | ApiError:
        if not raw_token:
            return unauthenticated()
        token = self._session.scalars(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(raw_token))
            .with_for_update()
        ).first()
        if token is None:
            return unauthenticated()
        now = self._clock.now()
        if token.revoked_at is not None:
            if token.replaced_by_id is not None:
                self._revoke_family(token.family_id, now)
                self._audit.record(
                    action="refresh_reuse_detected",
                    object_type="refresh_token",
                    object_id=token.family_id,
                    actor_id=token.user_id,
                )
            return unauthenticated()
        if token.expires_at <= now:
            return unauthenticated()
        user = self._session.get(User, token.user_id)
        if user is None or user.state is not AccountState.ACTIVE:
            self._revoke_family(token.family_id, now)
            return unauthenticated()
        replacement, raw_replacement = self._issue_refresh_token(user, token.family_id, now)
        token.revoked_at = now
        token.replaced_by_id = replacement.id
        token.updated_at = now
        access = create_access_token(user.id, now, self._settings)
        body = RefreshResponse(access_token=access.token, expires_in=access.expires_in)
        return RefreshGranted(body=body, refresh_token=raw_replacement)

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token = self._session.scalars(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(raw_token))
            .with_for_update()
        ).first()
        if token is None or token.revoked_at is not None:
            return
        self._revoke_family(token.family_id, self._clock.now())
        self._audit.record(
            action="logout", object_type="user", object_id=token.user_id, actor_id=token.user_id
        )

    def forgot_password(self, email: str) -> ApiError | None:
        retry_after = self._limiter.hit(FORGOT_PER_EMAIL, email)
        if retry_after is not None:
            return rate_limited(retry_after)
        user = self._session.scalars(select(User).where(User.email == email)).first()
        if user is None or user.state is not AccountState.ACTIVE:
            return None
        now = self._clock.now()
        raw = new_opaque_token()
        self._session.add(
            EmailToken(
                user_id=user.id,
                purpose=EmailTokenPurpose.RESET,
                token_hash=hash_token(raw),
                expires_at=now + RESET_TOKEN_LIFETIME,
                created_at=now,
                updated_at=now,
            )
        )
        self._enqueue_reset_email(user, raw)
        self._session.flush()
        return None

    def reset_password(self, raw_token: str, password: str) -> None:
        now = self._clock.now()
        token = self._session.scalars(
            select(EmailToken)
            .where(
                EmailToken.token_hash == hash_token(raw_token),
                EmailToken.purpose == EmailTokenPurpose.RESET,
            )
            .with_for_update()
        ).first()
        if token is None or token.used_at is not None:
            raise validation_error({"token": INVALID_RESET_TOKEN})
        if token.expires_at <= now:
            raise token_expired()
        policy_error = password_policy_error(password)
        if policy_error is not None:
            raise validation_error({"password": policy_error})
        user = self._session.get(User, token.user_id, with_for_update=True)
        if user is None or user.state is not AccountState.ACTIVE:
            raise validation_error({"token": INVALID_RESET_TOKEN})
        user.password_hash = hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        user.updated_at = now
        token.used_at = now
        token.updated_at = now
        self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, updated_at=now)
        )
        self._audit.record(
            action="password_reset", object_type="user", object_id=user.id, actor_id=user.id
        )

    def _grant(self, user: User, actor: Actor) -> LoginGranted:
        now = self._clock.now()
        user.last_login_at = now
        user.updated_at = now
        self._audit.record(
            action="login_succeeded", object_type="user", object_id=user.id, actor_id=user.id
        )
        raw_refresh = self._issue_refresh_token(user, uuid.uuid4(), now)[1]
        access = create_access_token(user.id, now, self._settings)
        body = LoginSuccess(
            access_token=access.token, expires_in=access.expires_in, user=self._me.me(actor)
        )
        return LoginGranted(body=body, refresh_token=raw_refresh)

    def _login_rate_limit(self, email: str) -> int | None:
        context = get_request_context()
        waits = [self._limiter.hit(LOGIN_PER_EMAIL, email)]
        if context is not None and context.ip_address is not None:
            waits.append(self._limiter.hit(LOGIN_PER_IP, context.ip_address))
        exceeded = [wait for wait in waits if wait is not None]
        return max(exceeded) if exceeded else None

    def _register_failure(self, user: User, now: datetime) -> ApiError:
        user.failed_login_count += 1
        user.updated_at = now
        self._audit.record(
            action="login_failed", object_type="user", object_id=user.id, actor_id=user.id
        )
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.failed_login_count = 0
            user.locked_until = now + LOCKOUT_DURATION
            self._audit.record(
                action="account_locked",
                object_type="user",
                object_id=user.id,
                actor_id=user.id,
                new_value={"locked_until": user.locked_until},
            )
        self._session.flush()
        return invalid_credentials()

    def _rejection_reason(self, user: User) -> str | None:
        statement = (
            select(SignupRequest.decision_reason)
            .where(SignupRequest.user_id == user.id, SignupRequest.status == SignupStatus.REJECTED)
            .order_by(SignupRequest.decided_at.desc().nulls_last(), SignupRequest.created_at.desc())
            .limit(1)
        )
        return self._session.scalars(statement).first()

    def _issue_refresh_token(
        self, user: User, family_id: uuid.UUID, now: datetime
    ) -> tuple[RefreshToken, str]:
        raw = new_opaque_token()
        context = get_request_context()
        token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            family_id=family_id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(days=self._settings.refresh_token_days),
            user_agent=context.user_agent if context is not None else None,
            ip_address=context.ip_address if context is not None else None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(token)
        self._session.flush()
        return token, raw

    def _revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, updated_at=now)
        )

    def _enqueue_reset_email(self, user: User, raw_token: str) -> None:
        enqueue_email(
            self._session,
            self._clock,
            user.email,
            RESET_TEMPLATE,
            {
                "name": user.name,
                "token": raw_token,
                "expires_minutes": int(RESET_TOKEN_LIFETIME.total_seconds() // 60),
            },
        )
