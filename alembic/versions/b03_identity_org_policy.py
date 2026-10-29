import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b03_identity_org_policy"
down_revision: str | None = "b02_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_POLICY_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEFAULT_POLICY_CONFIG = {
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


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.String(length=6), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("escalation_contact_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id ~ '^[A-Z]{2,6}$'", name=op.f("ck_departments_code_format")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
    )
    op.create_index(
        op.f("ix_departments_escalation_contact_user_id"),
        "departments",
        ["escalation_contact_user_id"],
        unique=False,
    )
    op.create_table(
        "rate_limit_hits",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("count >= 0", name=op.f("ck_rate_limit_hits_count_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_limit_hits")),
    )
    op.create_index(
        "uq_rate_limit_hits_key_window_start",
        "rate_limit_hits",
        ["key", "window_start"],
        unique=True,
    )
    op.create_table(
        "categories",
        sa.Column("department_id", sa.String(length=6), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_confidential", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_categories_department_id_departments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index(
        op.f("ix_categories_department_id"), "categories", ["department_id"], unique=False
    )
    op.create_index(
        "uq_categories_department_id_lower_name",
        "categories",
        ["department_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("home_department_id", sa.String(length=6), nullable=False),
        sa.Column(
            "global_role",
            sa.Enum(
                "super_admin",
                "admin",
                "spoke",
                "employee",
                name="global_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                "pending_verification",
                "pending_approval",
                "active",
                "rejected",
                "deactivated",
                name="account_state",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivation_reason", sa.Text(), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("mfa_failed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "theme",
            sa.Enum(
                "system",
                "light",
                "dark",
                name="theme",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("global_role <> 'spoke'", name=op.f("ck_users_global_role_not_spoke")),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.CheckConstraint(
            "failed_login_count >= 0", name=op.f("ck_users_failed_login_count_non_negative")
        ),
        sa.CheckConstraint(
            "mfa_failed_count >= 0", name=op.f("ck_users_mfa_failed_count_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"], ["users.id"], name=op.f("fk_users_approved_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["deactivated_by_id"], ["users.id"], name=op.f("fk_users_deactivated_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["home_department_id"],
            ["departments.id"],
            name=op.f("fk_users_home_department_id_departments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_approved_by_id"), "users", ["approved_by_id"], unique=False)
    op.create_index(
        op.f("ix_users_deactivated_by_id"), "users", ["deactivated_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_users_home_department_id"), "users", ["home_department_id"], unique=False
    )
    op.create_index(
        "uq_users_lower_email", "users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_foreign_key(
        op.f("fk_departments_escalation_contact_user_id_users"),
        "departments",
        "users",
        ["escalation_contact_user_id"],
        ["id"],
    )
    op.create_table(
        "confidential_grants",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_id", sa.Uuid(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_confidential_grants_category_id_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_id"], ["users.id"], name=op.f("fk_confidential_grants_granted_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"], ["users.id"], name=op.f("fk_confidential_grants_revoked_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_confidential_grants_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_confidential_grants")),
    )
    op.create_index(
        op.f("ix_confidential_grants_category_id"),
        "confidential_grants",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_confidential_grants_granted_by_id"),
        "confidential_grants",
        ["granted_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_confidential_grants_revoked_by_id"),
        "confidential_grants",
        ["revoked_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_confidential_grants_user_id"), "confidential_grants", ["user_id"], unique=False
    )
    op.create_index(
        "uq_confidential_grants_active",
        "confidential_grants",
        ["user_id", "category_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "email_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum(
                "verify",
                "reset",
                name="email_token_purpose",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_email_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_tokens_token_hash")),
    )
    op.create_index(op.f("ix_email_tokens_user_id"), "email_tokens", ["user_id"], unique=False)
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_mfa_recovery_codes_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_recovery_codes")),
    )
    op.create_index(
        op.f("ix_mfa_recovery_codes_user_id"), "mfa_recovery_codes", ["user_id"], unique=False
    )
    op.create_table(
        "policy_versions",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("version >= 1", name=op.f("ck_policy_versions_version_positive")),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_policy_versions_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_versions")),
        sa.UniqueConstraint("version", name=op.f("uq_policy_versions_version")),
    )
    op.create_index(
        op.f("ix_policy_versions_created_by_id"), "policy_versions", ["created_by_id"], unique=False
    )
    op.create_table(
        "protected_action_requests",
        sa.Column(
            "kind",
            sa.Enum(
                "deactivate_super_admin",
                "demote_super_admin",
                name="protected_action_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                "expired",
                name="protected_action_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decided_by_id IS NULL OR "
            "(decided_by_id <> requested_by_id AND decided_by_id <> target_user_id)",
            name=op.f("ck_protected_action_requests_decider_is_independent"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_protected_action_requests_decided_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_protected_action_requests_requested_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_protected_action_requests_target_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_protected_action_requests")),
    )
    op.create_index(
        op.f("ix_protected_action_requests_decided_by_id"),
        "protected_action_requests",
        ["decided_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_protected_action_requests_requested_by_id"),
        "protected_action_requests",
        ["requested_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_protected_action_requests_target_user_id"),
        "protected_action_requests",
        ["target_user_id"],
        unique=False,
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replaced_by_id_refresh_tokens"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_tokens_replaced_by_id"), "refresh_tokens", ["replaced_by_id"], unique=False
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_table(
        "signup_requests",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "requested_role",
            sa.Enum(
                "super_admin",
                "admin",
                "spoke",
                "employee",
                name="requested_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("requested_department_id", sa.String(length=6), nullable=False),
        sa.Column(
            "approved_role",
            sa.Enum(
                "super_admin",
                "admin",
                "spoke",
                "employee",
                name="approved_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("approved_department_id", sa.String(length=6), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                name="signup_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "requested_role <> 'spoke'", name=op.f("ck_signup_requests_requested_role_not_spoke")
        ),
        sa.ForeignKeyConstraint(
            ["approved_department_id"],
            ["departments.id"],
            name=op.f("fk_signup_requests_approved_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["users.id"], name=op.f("fk_signup_requests_decided_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["requested_department_id"],
            ["departments.id"],
            name=op.f("fk_signup_requests_requested_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_signup_requests_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signup_requests")),
    )
    op.create_index(
        op.f("ix_signup_requests_approved_department_id"),
        "signup_requests",
        ["approved_department_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_signup_requests_decided_by_id"), "signup_requests", ["decided_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_signup_requests_requested_department_id"),
        "signup_requests",
        ["requested_department_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_signup_requests_user_id"), "signup_requests", ["user_id"], unique=False
    )
    op.create_index(
        "uq_signup_requests_one_pending",
        "signup_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "spoke_assignments",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.String(length=6), nullable=False),
        sa.Column("granted_by_id", sa.Uuid(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_spoke_assignments_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_id"], ["users.id"], name=op.f("fk_spoke_assignments_granted_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"], ["users.id"], name=op.f("fk_spoke_assignments_revoked_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_spoke_assignments_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spoke_assignments")),
    )
    op.create_index(
        op.f("ix_spoke_assignments_department_id"),
        "spoke_assignments",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spoke_assignments_granted_by_id"),
        "spoke_assignments",
        ["granted_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spoke_assignments_revoked_by_id"),
        "spoke_assignments",
        ["revoked_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spoke_assignments_user_id"), "spoke_assignments", ["user_id"], unique=False
    )
    op.create_index(
        "uq_spoke_assignments_active",
        "spoke_assignments",
        ["user_id", "department_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    policy_versions = sa.table(
        "policy_versions",
        sa.column("id", sa.Uuid()),
        sa.column("version", sa.Integer()),
        sa.column("config", postgresql.JSONB()),
        sa.column("created_by_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        policy_versions.insert().values(
            id=DEFAULT_POLICY_ID,
            version=1,
            config=DEFAULT_POLICY_CONFIG,
            created_by_id=None,
            created_at=sa.func.now(),
        )
    )


def downgrade() -> None:
    op.drop_index(
        "uq_spoke_assignments_active",
        table_name="spoke_assignments",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.drop_index(op.f("ix_spoke_assignments_user_id"), table_name="spoke_assignments")
    op.drop_index(op.f("ix_spoke_assignments_revoked_by_id"), table_name="spoke_assignments")
    op.drop_index(op.f("ix_spoke_assignments_granted_by_id"), table_name="spoke_assignments")
    op.drop_index(op.f("ix_spoke_assignments_department_id"), table_name="spoke_assignments")
    op.drop_table("spoke_assignments")
    op.drop_index(
        "uq_signup_requests_one_pending",
        table_name="signup_requests",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(op.f("ix_signup_requests_user_id"), table_name="signup_requests")
    op.drop_index(op.f("ix_signup_requests_requested_department_id"), table_name="signup_requests")
    op.drop_index(op.f("ix_signup_requests_decided_by_id"), table_name="signup_requests")
    op.drop_index(op.f("ix_signup_requests_approved_department_id"), table_name="signup_requests")
    op.drop_table("signup_requests")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_replaced_by_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(
        op.f("ix_protected_action_requests_target_user_id"), table_name="protected_action_requests"
    )
    op.drop_index(
        op.f("ix_protected_action_requests_requested_by_id"), table_name="protected_action_requests"
    )
    op.drop_index(
        op.f("ix_protected_action_requests_decided_by_id"), table_name="protected_action_requests"
    )
    op.drop_table("protected_action_requests")
    op.drop_index(op.f("ix_policy_versions_created_by_id"), table_name="policy_versions")
    op.drop_table("policy_versions")
    op.drop_index(op.f("ix_mfa_recovery_codes_user_id"), table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_index(op.f("ix_email_tokens_user_id"), table_name="email_tokens")
    op.drop_table("email_tokens")
    op.drop_index(
        "uq_confidential_grants_active",
        table_name="confidential_grants",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.drop_index(op.f("ix_confidential_grants_user_id"), table_name="confidential_grants")
    op.drop_index(op.f("ix_confidential_grants_revoked_by_id"), table_name="confidential_grants")
    op.drop_index(op.f("ix_confidential_grants_granted_by_id"), table_name="confidential_grants")
    op.drop_index(op.f("ix_confidential_grants_category_id"), table_name="confidential_grants")
    op.drop_table("confidential_grants")
    op.drop_constraint(
        op.f("fk_departments_escalation_contact_user_id_users"), "departments", type_="foreignkey"
    )
    op.drop_index("uq_users_lower_email", table_name="users")
    op.drop_index(op.f("ix_users_home_department_id"), table_name="users")
    op.drop_index(op.f("ix_users_deactivated_by_id"), table_name="users")
    op.drop_index(op.f("ix_users_approved_by_id"), table_name="users")
    op.drop_table("users")
    op.drop_index("uq_categories_department_id_lower_name", table_name="categories")
    op.drop_index(op.f("ix_categories_department_id"), table_name="categories")
    op.drop_table("categories")
    op.drop_index("uq_rate_limit_hits_key_window_start", table_name="rate_limit_hits")
    op.drop_table("rate_limit_hits")
    op.drop_index(op.f("ix_departments_escalation_contact_user_id"), table_name="departments")
    op.drop_table("departments")
