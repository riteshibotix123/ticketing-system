import math
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.enums import AccountState, Role, SignupStatus
from app.core.errors import (
    ApiError,
    ErrorCode,
    conflict,
    forbidden,
    not_found,
    rate_limited,
    token_expired,
    too_many_attempts,
    validation_error,
)
from app.core.events import SignupDecided, SignupVerified, publish
from app.core.pagination import PageParams, fetch_page
from app.core.request_context import get_request_context
from app.core.security import (
    dummy_verify,
    hash_password,
    hash_token,
    new_opaque_token,
    password_policy_error,
    verify_password,
)
from app.models.identity import EmailToken, EmailTokenPurpose, SignupRequest, User
from app.models.org import Department
from app.policy import Actor
from app.policy.flags import USERS_APPROVE_EMPLOYEE, has_permission
from app.policy.permissions import can_decide_signup
from app.schemas.common import Page, UserRef
from app.schemas.signup import (
    ApproveSignupBody,
    ReapplyBody,
    SignupAccepted,
    SignupBody,
    SignupRequestOut,
)
from app.services.audit import AuditService
from app.services.auth import LOCKOUT_DURATION, MAX_FAILED_LOGINS
from app.services.email_outbox import enqueue_email
from app.services.policy import PolicyService
from app.services.rate_limit import RateLimit, RateLimiter

VERIFY_TOKEN_LIFETIME = timedelta(hours=24)
SIGNUP_PER_IP = RateLimit("signup:ip", 5, timedelta(hours=1))
SIGNUP_PER_EMAIL = RateLimit("signup:email", 5, timedelta(hours=1))
RESEND_PER_EMAIL = RateLimit("resend:email", 3, timedelta(hours=1))
SIGNUP_MESSAGE = "If the details are valid, check your email to continue."
INVALID_VERIFY_TOKEN = "This link is invalid or has already been used"
INACTIVE_DEPARTMENT = "Choose an active department"
WRONG_PASSWORD = "Incorrect email or password"


def _retry_after(until: datetime, now: datetime) -> int:
    return max(1, math.ceil((until - now).total_seconds()))


def _user_ref(user: User) -> UserRef:
    return UserRef(id=str(user.id), name=user.name, email=user.email, title=user.title)


class SignupService:
    def __init__(self, session: Session, clock: Clock, settings: Settings) -> None:
        self._session = session
        self._clock = clock
        self._settings = settings
        self._audit = AuditService(session, clock)
        self._limiter = RateLimiter(session, clock)

    def signup(self, body: SignupBody) -> SignupAccepted | ApiError:
        self._check_domain(body.email)
        policy_error = password_policy_error(body.password)
        if policy_error is not None:
            raise validation_error({"password": policy_error})
        self._check_department(body.requested_department, "requested_department")
        retry_after = self._signup_rate_limit(body.email)
        if retry_after is not None:
            return rate_limited(retry_after)
        accepted = SignupAccepted(message=SIGNUP_MESSAGE)
        now = self._clock.now()
        existing = self._session.scalars(
            select(User).where(User.email == body.email).with_for_update()
        ).first()
        if existing is not None:
            if existing.state is AccountState.PENDING_VERIFICATION:
                self._issue_verification(existing, now)
            else:
                enqueue_email(
                    self._session,
                    self._clock,
                    existing.email,
                    "account_exists_notice",
                    {"name": existing.name},
                )
            return accepted
        user = User(
            email=body.email,
            name=body.name,
            password_hash=hash_password(body.password),
            home_department_id=body.requested_department,
            global_role=Role.EMPLOYEE,
            state=AccountState.PENDING_VERIFICATION,
            created_at=now,
            updated_at=now,
        )
        self._session.add(user)
        self._session.flush()
        request = SignupRequest(
            user_id=user.id,
            requested_role=body.requested_role,
            requested_department_id=body.requested_department,
            status=SignupStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._session.add(request)
        self._session.flush()
        self._audit.record(
            action="signup_requested",
            object_type="signup_request",
            object_id=request.id,
            actor_id=user.id,
            new_value={
                "requested_role": body.requested_role,
                "requested_department": body.requested_department,
            },
        )
        self._issue_verification(user, now)
        return accepted

    def verify_email(self, raw_token: str) -> AccountState:
        now = self._clock.now()
        token = self._session.scalars(
            select(EmailToken)
            .where(
                EmailToken.token_hash == hash_token(raw_token),
                EmailToken.purpose == EmailTokenPurpose.VERIFY,
            )
            .with_for_update()
        ).first()
        if token is None or token.used_at is not None:
            raise validation_error({"token": INVALID_VERIFY_TOKEN})
        if token.expires_at <= now:
            raise token_expired()
        user = self._session.get(User, token.user_id, with_for_update=True)
        if user is None or user.state is not AccountState.PENDING_VERIFICATION:
            raise validation_error({"token": INVALID_VERIFY_TOKEN})
        request = self._pending_request(user.id)
        if request is None:
            raise validation_error({"token": INVALID_VERIFY_TOKEN})
        token.used_at = now
        token.updated_at = now
        user.email_verified_at = now
        user.state = AccountState.PENDING_APPROVAL
        user.updated_at = now
        self._audit.record(
            action="email_verified",
            object_type="user",
            object_id=user.id,
            actor_id=user.id,
            old_value={"state": AccountState.PENDING_VERIFICATION},
            new_value={"state": AccountState.PENDING_APPROVAL},
        )
        publish(
            self._session,
            SignupVerified(actor_id=user.id, occurred_at=now, signup_request_id=request.id),
        )
        return user.state

    def resend_verification(self, email: str) -> ApiError | None:
        retry_after = self._limiter.hit(RESEND_PER_EMAIL, email)
        if retry_after is not None:
            return rate_limited(retry_after)
        user = self._session.scalars(
            select(User).where(User.email == email).with_for_update()
        ).first()
        if user is None or user.state is not AccountState.PENDING_VERIFICATION:
            return None
        self._issue_verification(user, self._clock.now())
        return None

    def reapply(self, body: ReapplyBody) -> ApiError | None:
        self._check_domain(body.email)
        self._check_department(body.requested_department, "requested_department")
        now = self._clock.now()
        user = self._session.scalars(
            select(User).where(User.email == body.email).with_for_update()
        ).first()
        if user is None:
            dummy_verify(body.password)
            return self._wrong_password()
        if user.locked_until is not None and user.locked_until > now:
            return too_many_attempts(_retry_after(user.locked_until, now))
        if not verify_password(user.password_hash, body.password):
            self._register_failure(user, now)
            return self._wrong_password()
        user.failed_login_count = 0
        user.locked_until = None
        user.updated_at = now
        if user.state is not AccountState.REJECTED:
            return conflict("Only a rejected account can reapply")
        request = SignupRequest(
            user_id=user.id,
            requested_role=body.requested_role,
            requested_department_id=body.requested_department,
            status=SignupStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._session.add(request)
        user.home_department_id = body.requested_department
        user.state = AccountState.PENDING_APPROVAL
        self._session.flush()
        self._audit.record(
            action="signup_reapplied",
            object_type="signup_request",
            object_id=request.id,
            actor_id=user.id,
            old_value={"state": AccountState.REJECTED},
            new_value={
                "state": AccountState.PENDING_APPROVAL,
                "requested_role": body.requested_role,
                "requested_department": body.requested_department,
            },
        )
        publish(
            self._session,
            SignupVerified(actor_id=user.id, occurred_at=now, signup_request_id=request.id),
        )
        return None

    def list_requests(
        self, actor: Actor, status: SignupStatus | None, params: PageParams
    ) -> Page[SignupRequestOut]:
        self._require_approver(actor)
        statement = (
            select(SignupRequest)
            .join(User, User.id == SignupRequest.user_id)
            .where(
                or_(
                    SignupRequest.status != SignupStatus.PENDING,
                    User.state == AccountState.PENDING_APPROVAL,
                )
            )
            .order_by(SignupRequest.created_at.desc(), SignupRequest.id.desc())
        )
        if status is not None:
            statement = statement.where(SignupRequest.status == status)
        result = fetch_page(self._session, statement, params)
        users = self._users(
            [request.user_id for request in result.items]
            + [request.decided_by_id for request in result.items if request.decided_by_id]
        )
        return Page[SignupRequestOut](
            items=[self._to_out(actor, request, users) for request in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def approve(self, actor: Actor, request_id: str, body: ApproveSignupBody) -> SignupRequestOut:
        self._require_approver(actor)
        request, user = self._load_for_decision(request_id)
        if not can_decide_signup(actor, request.requested_role, body.approved_role, user.id):
            raise forbidden()
        self._ensure_decidable(request, user)
        self._check_department(body.approved_department, "approved_department")
        now = self._clock.now()
        user.state = AccountState.ACTIVE
        user.global_role = body.approved_role
        user.home_department_id = body.approved_department
        user.approved_by_id = actor.id
        user.approved_at = now
        user.updated_at = now
        request.status = SignupStatus.APPROVED
        request.approved_role = body.approved_role
        request.approved_department_id = body.approved_department
        request.decided_by_id = actor.id
        request.decided_at = now
        request.updated_at = now
        self._session.flush()
        enqueue_email(
            self._session, self._clock, user.email, "signup_approved", {"name": user.name}
        )
        self._audit.record(
            action="signup_approved",
            object_type="signup_request",
            object_id=request.id,
            actor_id=actor.id,
            old_value={
                "requested_role": request.requested_role,
                "requested_department": request.requested_department_id,
            },
            new_value={
                "approved_role": body.approved_role,
                "approved_department": body.approved_department,
            },
            is_security_limited=True,
        )
        publish(
            self._session,
            SignupDecided(actor_id=actor.id, occurred_at=now, signup_request_id=request.id),
        )
        return self._to_out(actor, request, self._users([user.id, actor.id]))

    def reject(self, actor: Actor, request_id: str, reason: str) -> SignupRequestOut:
        self._require_approver(actor)
        request, user = self._load_for_decision(request_id)
        if not can_decide_signup(actor, request.requested_role, None, user.id):
            raise forbidden()
        self._ensure_decidable(request, user)
        now = self._clock.now()
        user.state = AccountState.REJECTED
        user.updated_at = now
        request.status = SignupStatus.REJECTED
        request.decision_reason = reason
        request.decided_by_id = actor.id
        request.decided_at = now
        request.updated_at = now
        self._session.flush()
        enqueue_email(
            self._session,
            self._clock,
            user.email,
            "signup_rejected",
            {"name": user.name, "reason": reason},
        )
        self._audit.record(
            action="signup_rejected",
            object_type="signup_request",
            object_id=request.id,
            actor_id=actor.id,
            reason=reason,
        )
        publish(
            self._session,
            SignupDecided(actor_id=actor.id, occurred_at=now, signup_request_id=request.id),
        )
        return self._to_out(actor, request, self._users([user.id, actor.id]))

    def _check_domain(self, email: str) -> None:
        domains = self._settings.allowed_email_domains
        domain = email.rsplit("@", 1)[-1]
        if domain not in domains:
            raise validation_error({"email": f"Use an email address at: {', '.join(domains)}"})

    def _check_department(self, department_id: str, field: str) -> None:
        department = self._session.get(Department, department_id)
        if department is None or not department.is_active:
            raise validation_error({field: INACTIVE_DEPARTMENT})

    def _signup_rate_limit(self, email: str) -> int | None:
        context = get_request_context()
        waits = [self._limiter.hit(SIGNUP_PER_EMAIL, email)]
        if context is not None and context.ip_address is not None:
            waits.append(self._limiter.hit(SIGNUP_PER_IP, context.ip_address))
        exceeded = [wait for wait in waits if wait is not None]
        return max(exceeded) if exceeded else None

    def _issue_verification(self, user: User, now: datetime) -> None:
        self._session.execute(
            update(EmailToken)
            .where(
                EmailToken.user_id == user.id,
                EmailToken.purpose == EmailTokenPurpose.VERIFY,
                EmailToken.used_at.is_(None),
            )
            .values(used_at=now, updated_at=now)
        )
        raw = new_opaque_token()
        self._session.add(
            EmailToken(
                user_id=user.id,
                purpose=EmailTokenPurpose.VERIFY,
                token_hash=hash_token(raw),
                expires_at=now + VERIFY_TOKEN_LIFETIME,
                created_at=now,
                updated_at=now,
            )
        )
        self._session.flush()
        hours = int(VERIFY_TOKEN_LIFETIME.total_seconds() // 3600)
        enqueue_email(
            self._session,
            self._clock,
            user.email,
            "verify_email",
            {"name": user.name, "token": raw, "expires_hours": hours},
        )

    def _wrong_password(self) -> ApiError:
        return ApiError(ErrorCode.FORBIDDEN, WRONG_PASSWORD, fields={"password": WRONG_PASSWORD})

    def _register_failure(self, user: User, now: datetime) -> None:
        user.failed_login_count += 1
        user.updated_at = now
        self._audit.record(
            action="reapply_failed", object_type="user", object_id=user.id, actor_id=user.id
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

    def _pending_request(self, user_id: uuid.UUID) -> SignupRequest | None:
        return self._session.scalars(
            select(SignupRequest)
            .where(SignupRequest.user_id == user_id, SignupRequest.status == SignupStatus.PENDING)
            .with_for_update()
        ).first()

    def _require_approver(self, actor: Actor) -> None:
        policy = PolicyService(self._session).current()
        if not has_permission(actor, USERS_APPROVE_EMPLOYEE, policy.admins_can_manage_departments):
            raise forbidden()

    def _load_for_decision(self, request_id: str) -> tuple[SignupRequest, User]:
        try:
            parsed = uuid.UUID(request_id)
        except ValueError as exc:
            raise not_found() from exc
        request = self._session.get(SignupRequest, parsed, with_for_update=True)
        if request is None:
            raise not_found()
        user = self._session.get(User, request.user_id, with_for_update=True)
        if user is None:
            raise not_found()
        return request, user

    def _ensure_decidable(self, request: SignupRequest, user: User) -> None:
        if request.status is not SignupStatus.PENDING:
            raise conflict("This signup request has already been decided")
        if user.state is not AccountState.PENDING_APPROVAL:
            raise conflict("This signup request is not awaiting approval")

    def _users(self, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, User]:
        wanted = set(ids)
        if not wanted:
            return {}
        users = self._session.scalars(select(User).where(User.id.in_(wanted)))
        return {user.id: user for user in users}

    def _to_out(
        self, actor: Actor, request: SignupRequest, users: dict[uuid.UUID, User]
    ) -> SignupRequestOut:
        applicant = users[request.user_id]
        decider = users.get(request.decided_by_id) if request.decided_by_id else None
        can_approve = request.status is SignupStatus.PENDING and can_decide_signup(
            actor, request.requested_role, None, applicant.id
        )
        return SignupRequestOut(
            id=str(request.id),
            name=applicant.name,
            email=applicant.email,
            email_verified=applicant.email_verified_at is not None,
            requested_role=request.requested_role,
            requested_department=request.requested_department_id,
            approved_role=request.approved_role,
            approved_department=request.approved_department_id,
            status=request.status,
            decided_by=_user_ref(decider) if decider is not None else None,
            decided_at=request.decided_at,
            rejection_reason=request.decision_reason,
            created_at=request.created_at,
            can_approve=can_approve,
        )
