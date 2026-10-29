import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    AccountState,
    ProtectedActionKind,
    ProtectedActionStatus,
    Role,
    SignupStatus,
)
from app.models.base import Base, Timestamps, UuidPk, enum_type


class EmailTokenPurpose(StrEnum):
    VERIFY = "verify"
    RESET = "reset"


class Theme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class User(UuidPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("global_role <> 'spoke'", name="global_role_not_spoke"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
        CheckConstraint("mfa_failed_count >= 0", name="mfa_failed_count_non_negative"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    home_department_id: Mapped[str] = mapped_column(
        String(6), ForeignKey("departments.id"), nullable=False, index=True
    )
    global_role: Mapped[Role] = mapped_column(
        enum_type(Role, "global_role"), nullable=False, default=Role.EMPLOYEE
    )
    state: Mapped[AccountState] = mapped_column(
        enum_type(AccountState, "account_state"), nullable=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    theme: Mapped[Theme | None] = mapped_column(enum_type(Theme, "theme"), nullable=True)


class MfaRecoveryCode(UuidPk, Timestamps, Base):
    __tablename__ = "mfa_recovery_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SignupRequest(UuidPk, Timestamps, Base):
    __tablename__ = "signup_requests"
    __table_args__ = (
        CheckConstraint("requested_role <> 'spoke'", name="requested_role_not_spoke"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    requested_role: Mapped[Role] = mapped_column(enum_type(Role, "requested_role"), nullable=False)
    requested_department_id: Mapped[str] = mapped_column(
        String(6), ForeignKey("departments.id"), nullable=False, index=True
    )
    approved_role: Mapped[Role | None] = mapped_column(
        enum_type(Role, "approved_role"), nullable=True
    )
    approved_department_id: Mapped[str | None] = mapped_column(
        String(6), ForeignKey("departments.id"), nullable=True, index=True
    )
    status: Mapped[SignupStatus] = mapped_column(
        enum_type(SignupStatus, "signup_status"), nullable=False, default=SignupStatus.PENDING
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailToken(UuidPk, Timestamps, Base):
    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        enum_type(EmailTokenPurpose, "email_token_purpose"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(UuidPk, Timestamps, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("refresh_tokens.id"), nullable=True, index=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)


class ProtectedActionRequest(UuidPk, Timestamps, Base):
    __tablename__ = "protected_action_requests"
    __table_args__ = (
        CheckConstraint(
            "decided_by_id IS NULL OR "
            "(decided_by_id <> requested_by_id AND decided_by_id <> target_user_id)",
            name="decider_is_independent",
        ),
    )

    kind: Mapped[ProtectedActionKind] = mapped_column(
        enum_type(ProtectedActionKind, "protected_action_kind"), nullable=False
    )
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[ProtectedActionStatus] = mapped_column(
        enum_type(ProtectedActionStatus, "protected_action_status"),
        nullable=False,
        default=ProtectedActionStatus.PENDING,
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RateLimitHit(UuidPk, Base):
    __tablename__ = "rate_limit_hits"
    __table_args__ = (CheckConstraint("count >= 0", name="count_non_negative"),)

    key: Mapped[str] = mapped_column(String(255), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


Index("uq_users_lower_email", func.lower(User.email), unique=True)
Index(
    "uq_signup_requests_one_pending",
    SignupRequest.user_id,
    unique=True,
    postgresql_where=text("status = 'pending'"),
)
Index(
    "uq_rate_limit_hits_key_window_start",
    RateLimitHit.key,
    RateLimitHit.window_start,
    unique=True,
)
