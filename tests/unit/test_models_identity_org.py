from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint, func, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core.enums import AccountState, ProtectedActionStatus, Role, SignupStatus
from app.models import (
    Base,
    Department,
    EmailTokenPurpose,
    PolicyVersion,
    SignupRequest,
    User,
)
from tests.factories import (
    FACTORY_NOW,
    make_category,
    make_confidential_grant,
    make_department,
    make_email_token,
    make_policy_version,
    make_protected_action,
    make_rate_limit_hit,
    make_refresh_token,
    make_signup_request,
    make_spoke_assignment,
    make_user,
)

DEFAULT_POLICY = {
    "initial_response_hours": 24,
    "warning_hours": {"low": 18, "medium": 18, "high": 18, "critical": 12},
    "l3_hours": {"low": 48, "medium": 48, "high": 36, "critical": 30},
    "update_warning_hours": 20,
    "update_cadence_hours": 24,
    "eta_warning_hours": 2,
    "escalation_repeat_hours": 24,
    "requester_reminder_hours": 48,
    "auto_close_business_days": 3,
    "reopen_window_days": 7,
    "max_reopens": 3,
    "sla_mode": "calendar",
    "admins_can_manage_departments": True,
}


def _in_savepoint(db: Session, action: Callable[[], object]) -> None:
    with db.begin_nested():
        action()
        db.flush()


def _violates(
    db: Session,
    action: Callable[[], object],
    expected: type[DBAPIError] = IntegrityError,
) -> None:
    with pytest.raises(expected):
        _in_savepoint(db, action)


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT")


@pytest.fixture
def hr(db: Session) -> Department:
    return make_department(db, "HR")


@pytest.fixture
def user(db: Session, it: Department) -> User:
    return make_user(db, it)


def test_factories_create_rows(db: Session, it: Department, user: User) -> None:
    admin = make_user(db, it, role=Role.ADMIN)
    category = make_category(db, it, "Hardware")
    make_spoke_assignment(db, user, it, granted_by=admin)
    make_confidential_grant(db, user, category, granted_by=admin)
    make_signup_request(db, make_user(db, it, state=AccountState.PENDING_APPROVAL), it)
    make_email_token(db, user)
    make_refresh_token(db, user)
    make_protected_action(db, admin, user)
    make_rate_limit_hit(db, "login:user@ibotix.ai")
    assert db.scalar(select(func.count()).select_from(User)) == 3
    assert user.global_role is Role.EMPLOYEE
    assert user.failed_login_count == 0
    assert user.mfa_enabled is False


def test_enum_columns_store_lowercase_values(db: Session, it: Department) -> None:
    admin = make_user(db, it, role=Role.SUPER_ADMIN)
    stored = db.execute(
        text("SELECT global_role, state FROM users WHERE id = :id"), {"id": admin.id}
    ).one()
    assert tuple(stored) == ("super_admin", "active")


@pytest.mark.usefixtures("it")
def test_server_defaults(db: Session) -> None:
    row = db.execute(
        text(
            "INSERT INTO users (id, email, name, password_hash, home_department_id, "
            "global_role, state, created_at, updated_at) VALUES (gen_random_uuid(), "
            "'raw@ibotix.ai', 'Raw', 'x', 'IT', 'employee', 'active', now(), now()) "
            "RETURNING failed_login_count, mfa_enabled, mfa_failed_count"
        )
    ).one()
    assert tuple(row) == (0, False, 0)
    inactive = db.execute(
        text(
            "INSERT INTO departments (id, name, created_at, updated_at) "
            "VALUES ('OPS', 'Ops', now(), now()) RETURNING is_active"
        )
    ).scalar_one()
    assert inactive is False


@pytest.mark.parametrize("code", ["it", "I", "TOOLONG", "I1", "I-T"])
def test_department_code_format(db: Session, code: str) -> None:
    _violates(db, lambda: make_department(db, code), DBAPIError)


def test_department_code_accepts_valid(db: Session) -> None:
    assert make_department(db, "FINOPS").id == "FINOPS"


def test_user_email_unique_case_insensitive(db: Session, it: Department) -> None:
    make_user(db, it, email="asha@ibotix.ai")
    _violates(db, lambda: make_user(db, it, email="asha@ibotix.ai"))


def test_user_email_must_be_lowercase(db: Session, it: Department) -> None:
    _violates(db, lambda: make_user(db, it, email="Asha@ibotix.ai"))


def test_user_global_role_cannot_be_spoke(db: Session, it: Department) -> None:
    _violates(db, lambda: make_user(db, it, role=Role.SPOKE))


@pytest.mark.usefixtures("it")
def test_user_role_rejects_unknown_value(db: Session) -> None:
    with pytest.raises(IntegrityError):
        _in_savepoint(
            db,
            lambda: db.execute(
                text(
                    "INSERT INTO users (id, email, name, password_hash, home_department_id, "
                    "global_role, state, created_at, updated_at) VALUES (gen_random_uuid(), "
                    "'bad@ibotix.ai', 'Bad', 'x', 'IT', 'resolver', 'active', now(), now())"
                )
            ),
        )


def test_orm_rejects_unknown_enum_string(db: Session, it: Department) -> None:
    statement = insert(User).values(
        email="x@ibotix.ai",
        name="X",
        password_hash="x",
        home_department_id=it.id,
        global_role="resolver",
        state="active",
        created_at=FACTORY_NOW,
        updated_at=FACTORY_NOW,
    )
    with pytest.raises(StatementError):
        _in_savepoint(db, lambda: db.execute(statement))


def test_user_home_department_required(db: Session) -> None:
    _violates(
        db,
        lambda: db.add(
            User(
                email="nodept@ibotix.ai",
                name="No Dept",
                password_hash="x",
                home_department_id="ZZ",
                global_role=Role.EMPLOYEE,
                state=AccountState.ACTIVE,
                created_at=FACTORY_NOW,
                updated_at=FACTORY_NOW,
            )
        ),
    )


def test_one_pending_signup_request_per_user(db: Session, it: Department) -> None:
    applicant = make_user(db, it, state=AccountState.PENDING_APPROVAL)
    make_signup_request(db, applicant, it)
    _violates(db, lambda: make_signup_request(db, applicant, it))


def test_rejected_signup_allows_new_pending(db: Session, it: Department) -> None:
    applicant = make_user(db, it, state=AccountState.REJECTED)
    make_signup_request(db, applicant, it, status=SignupStatus.REJECTED)
    make_signup_request(db, applicant, it, status=SignupStatus.REJECTED)
    pending = make_signup_request(db, applicant, it)
    assert pending.status is SignupStatus.PENDING
    count = db.scalar(
        select(func.count()).select_from(SignupRequest).where(SignupRequest.user_id == applicant.id)
    )
    assert count == 3


def test_signup_requested_role_cannot_be_spoke(db: Session, it: Department, user: User) -> None:
    _violates(db, lambda: make_signup_request(db, user, it, requested_role=Role.SPOKE))


def test_email_token_hash_unique(db: Session, user: User) -> None:
    make_email_token(db, user, raw_token="same")
    _violates(
        db,
        lambda: make_email_token(db, user, raw_token="same", purpose=EmailTokenPurpose.RESET),
    )


def test_refresh_token_hash_unique(db: Session, user: User) -> None:
    make_refresh_token(db, user, raw_token="same")
    _violates(db, lambda: make_refresh_token(db, user, raw_token="same"))


def test_active_spoke_assignment_unique(db: Session, it: Department, user: User) -> None:
    make_spoke_assignment(db, user, it)
    _violates(db, lambda: make_spoke_assignment(db, user, it))


def test_revoked_spoke_assignment_allows_new(
    db: Session, it: Department, hr: Department, user: User
) -> None:
    make_spoke_assignment(db, user, it, revoked_at=FACTORY_NOW)
    make_spoke_assignment(db, user, it, revoked_at=FACTORY_NOW + timedelta(days=1))
    make_spoke_assignment(db, user, it)
    make_spoke_assignment(db, user, hr)


def test_category_name_unique_per_department_case_insensitive(
    db: Session, it: Department, hr: Department
) -> None:
    make_category(db, it, "Hardware")
    make_category(db, hr, "Hardware")
    _violates(db, lambda: make_category(db, it, "hardware"))


def test_active_confidential_grant_unique(db: Session, it: Department, user: User) -> None:
    category = make_category(db, it, "Payroll", is_confidential=True)
    make_confidential_grant(db, user, category)
    _violates(db, lambda: make_confidential_grant(db, user, category))


def test_revoked_confidential_grant_allows_new(db: Session, it: Department, user: User) -> None:
    category = make_category(db, it, "Payroll", is_confidential=True)
    make_confidential_grant(db, user, category, revoked_at=FACTORY_NOW)
    make_confidential_grant(db, user, category)


def test_protected_action_decider_must_be_independent(
    db: Session, it: Department, user: User
) -> None:
    target = make_user(db, it, role=Role.SUPER_ADMIN)
    action = make_protected_action(db, target, user)

    def decide_by(decider: User) -> None:
        action.decided_by_id = decider.id
        action.status = ProtectedActionStatus.APPROVED

    _violates(db, lambda: decide_by(user))
    db.refresh(action)
    _violates(db, lambda: decide_by(target))
    db.refresh(action)
    independent = make_user(db, it, role=Role.SUPER_ADMIN)
    _in_savepoint(db, lambda: decide_by(independent))
    assert action.decided_by_id == independent.id


def test_rate_limit_window_unique(db: Session) -> None:
    make_rate_limit_hit(db, "login:a")
    make_rate_limit_hit(db, "login:a", window_start=FACTORY_NOW + timedelta(minutes=1))
    make_rate_limit_hit(db, "login:b")
    _violates(db, lambda: make_rate_limit_hit(db, "login:a"))


def test_rate_limit_count_non_negative(db: Session) -> None:
    _violates(db, lambda: make_rate_limit_hit(db, "login:c", count=-1))


def test_default_policy_present(db: Session) -> None:
    policy = db.scalars(select(PolicyVersion).order_by(PolicyVersion.version.desc())).first()
    assert policy is not None
    assert policy.version == 1
    assert policy.created_by_id is None
    assert policy.config == DEFAULT_POLICY


def test_policy_version_unique(db: Session) -> None:
    _violates(db, lambda: make_policy_version(db, 1, {"sla_mode": "calendar"}))


def test_policy_version_positive(db: Session) -> None:
    _violates(db, lambda: make_policy_version(db, 0, {"sla_mode": "calendar"}))


def test_every_foreign_key_is_indexed() -> None:
    for table in Base.metadata.sorted_tables:
        leading = {index.columns[0].name for index in table.indexes if len(index.columns) > 0}
        leading |= {
            constraint.columns[0].name
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint | PrimaryKeyConstraint)
            and len(constraint.columns) > 0
        }
        for fk in table.foreign_key_constraints:
            column = fk.column_keys[0]
            assert column in leading, f"{table.name}.{column} is not indexed"


def test_every_datetime_is_timestamptz(db: Session) -> None:
    rows = db.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'timestamp without time zone'"
        )
    ).all()
    assert rows == []
