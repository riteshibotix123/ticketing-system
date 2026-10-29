from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b05_audit_log"
down_revision: str | None = "b04_tickets_sla_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AUDIT_IMMUTABLE_FUNCTION = """
CREATE FUNCTION reject_audit_log_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log rows are immutable' USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql
"""

AUDIT_IMMUTABLE_TRIGGER = """
CREATE TRIGGER audit_log_immutable
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION reject_audit_log_change()
"""

IMMUTABLE_TABLES = ("audit_log", "ticket_events")


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=True),
        sa.Column(
            "old_value", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "new_value", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.String(length=6), nullable=True),
        sa.Column(
            "is_security_limited", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_confidential_ticket", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_log_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_audit_log_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_audit_log_ticket_id_tickets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"], unique=False)
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_audit_log_department_id"), "audit_log", ["department_id"], unique=False
    )
    op.create_index(
        "ix_audit_log_object_type_object_id",
        "audit_log",
        ["object_type", "object_id"],
        unique=False,
    )
    op.create_index(op.f("ix_audit_log_ticket_id"), "audit_log", ["ticket_id"], unique=False)

    op.execute(AUDIT_IMMUTABLE_FUNCTION)
    op.execute(AUDIT_IMMUTABLE_TRIGGER)
    for table in IMMUTABLE_TABLES:
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_log_immutable ON audit_log")
    op.execute("DROP FUNCTION reject_audit_log_change()")
    op.drop_index(op.f("ix_audit_log_ticket_id"), table_name="audit_log")
    op.drop_index("ix_audit_log_object_type_object_id", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_department_id"), table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
