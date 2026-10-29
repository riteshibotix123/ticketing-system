from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b04_tickets_sla_notifications"
down_revision: str | None = "b03_identity_org_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_FUNCTION = """
CREATE FUNCTION reject_ticket_event_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ticket_events rows are immutable' USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql
"""

IMMUTABLE_TRIGGER = """
CREATE TRIGGER ticket_events_immutable
BEFORE UPDATE OR DELETE ON ticket_events
FOR EACH ROW EXECUTE FUNCTION reject_ticket_event_change()
"""


def upgrade() -> None:
    op.create_table(
        "ticket_counters",
        sa.Column("department_code", sa.String(length=6), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "department_code ~ '^[A-Z]{2,6}$'",
            name=op.f("ck_ticket_counters_department_code_format"),
        ),
        sa.CheckConstraint(
            "last_value >= 0", name=op.f("ck_ticket_counters_last_value_non_negative")
        ),
        sa.CheckConstraint(
            "year BETWEEN 1000 AND 9999", name=op.f("ck_ticket_counters_year_four_digits")
        ),
        sa.PrimaryKeyConstraint("department_code", "year", name=op.f("pk_ticket_counters")),
    )
    op.create_table(
        "worker_heartbeat",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_worker_heartbeat")),
    )
    op.create_table(
        "tickets",
        sa.Column("ticket_no", sa.String(length=32), nullable=False),
        sa.Column("origin_department_code", sa.String(length=6), nullable=False),
        sa.Column("department_id", sa.String(length=6), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "requested_priority",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="requested_priority",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="priority",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("confidential", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "acknowledged",
                "assigned",
                "in_progress",
                "awaiting_requester",
                "on_hold",
                "resolved",
                "closed",
                "reopened",
                "cancelled",
                name="ticket_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("sla_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_checkpoint_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_team_update_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hold_reason", sa.Text(), nullable=True),
        sa.Column("hold_review_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("awaiting_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "close_reason",
            sa.Enum(
                "confirmed",
                "admin",
                "auto",
                name="close_reason",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("reopen_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("feedback_rating", sa.SmallInteger(), nullable=True),
        sa.Column("feedback_comment", sa.Text(), nullable=True),
        sa.Column(
            "escalation_level", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("update_overdue", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "origin_department_code ~ '^[A-Z]{2,6}$'",
            name=op.f("ck_tickets_origin_department_code_format"),
        ),
        sa.CheckConstraint(
            "ticket_no ~ '^IBX-[A-Z]{2,6}-[0-9]{4}-[0-9]{6}$'",
            name=op.f("ck_tickets_ticket_no_format"),
        ),
        sa.CheckConstraint(
            "escalation_level BETWEEN 0 AND 3", name=op.f("ck_tickets_escalation_level_range")
        ),
        sa.CheckConstraint(
            "feedback_rating IS NULL OR feedback_rating BETWEEN 1 AND 5",
            name=op.f("ck_tickets_feedback_rating_range"),
        ),
        sa.CheckConstraint("reopen_count >= 0", name=op.f("ck_tickets_reopen_count_non_negative")),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], name=op.f("fk_tickets_assignee_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name=op.f("fk_tickets_category_id_categories")
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name=op.f("fk_tickets_department_id_departments")
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_tickets_owner_id_users")),
        sa.ForeignKeyConstraint(
            ["requester_id"], ["users.id"], name=op.f("fk_tickets_requester_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("ticket_no", name=op.f("uq_tickets_ticket_no")),
    )
    op.create_index(op.f("ix_tickets_assignee_id"), "tickets", ["assignee_id"], unique=False)
    op.create_index(op.f("ix_tickets_category_id"), "tickets", ["category_id"], unique=False)
    op.create_index(
        "ix_tickets_department_id_status", "tickets", ["department_id", "status"], unique=False
    )
    op.create_index(
        "ix_tickets_escalation_level_priority",
        "tickets",
        ["escalation_level", "priority"],
        unique=False,
    )
    op.create_index(op.f("ix_tickets_eta"), "tickets", ["eta"], unique=False)
    op.create_index(op.f("ix_tickets_owner_id"), "tickets", ["owner_id"], unique=False)
    op.create_index(op.f("ix_tickets_requester_id"), "tickets", ["requester_id"], unique=False)
    op.create_index(op.f("ix_tickets_sla_started_at"), "tickets", ["sla_started_at"], unique=False)
    op.create_index(
        "ix_tickets_ticket_no_trgm",
        "tickets",
        ["ticket_no"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"ticket_no": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_tickets_title_trgm",
        "tickets",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index("ix_tickets_updated_at", "tickets", ["updated_at"], unique=False)
    op.create_table(
        "attachments",
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("uploader_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "scan_status",
            sa.Enum(
                "pending",
                "clean",
                "infected",
                name="scan_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_attachments_size_bytes_non_negative")),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_attachments_ticket_id_tickets")
        ),
        sa.ForeignKeyConstraint(
            ["uploader_id"], ["users.id"], name=op.f("fk_attachments_uploader_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_attachments_storage_key")),
    )
    op.create_index(op.f("ix_attachments_ticket_id"), "attachments", ["ticket_id"], unique=False)
    op.create_index(
        "ix_attachments_unlinked_created_at",
        "attachments",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("ticket_id IS NULL"),
    )
    op.create_index(
        op.f("ix_attachments_uploader_id"), "attachments", ["uploader_id"], unique=False
    )
    op.create_table(
        "escalation_events",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column(
            "timer_kind",
            sa.Enum(
                "initial_response",
                "progress_update",
                "eta",
                "auto_close",
                "requester_reminder",
                "hold_review",
                name="escalation_timer_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("cycle", sa.Integer(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recipient_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("cycle >= 1", name=op.f("ck_escalation_events_cycle_positive")),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name=op.f("ck_escalation_events_level_range")),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_escalation_events_ticket_id_tickets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_escalation_events")),
        sa.UniqueConstraint(
            "ticket_id",
            "timer_kind",
            "cycle",
            "step_key",
            name=op.f("uq_escalation_events_ticket_id_timer_kind_cycle_step_key"),
        ),
    )
    op.create_table(
        "notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("critical", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_notifications_ticket_id_tickets")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        op.f("ix_notifications_ticket_id"), "notifications", ["ticket_id"], unique=False
    )
    op.create_index(
        "ix_notifications_user_id_read_at_created_at",
        "notifications",
        ["user_id", "read_at", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_notifications_user_id_dedupe_key",
        "notifications",
        ["user_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.create_table(
        "sla_timers",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "initial_response",
                "progress_update",
                "eta",
                "auto_close",
                "requester_reminder",
                "hold_review",
                name="timer_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("cycle", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("warning_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("l3_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("level", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("met_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("cycle >= 1", name=op.f("ck_sla_timers_cycle_positive")),
        sa.CheckConstraint("level BETWEEN 0 AND 3", name=op.f("ck_sla_timers_level_range")),
        sa.CheckConstraint(
            "paused_seconds >= 0", name=op.f("ck_sla_timers_paused_seconds_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_sla_timers_ticket_id_tickets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_timers")),
        sa.UniqueConstraint("ticket_id", "kind", name=op.f("uq_sla_timers_ticket_id_kind")),
    )
    op.create_index(
        "ix_sla_timers_active_due_at",
        "sla_timers",
        ["due_at"],
        unique=False,
        postgresql_where=sa.text("met_at IS NULL AND stopped_at IS NULL AND paused_at IS NULL"),
    )
    op.create_table(
        "ticket_collaborators",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("added_by_id", sa.Uuid(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["added_by_id"], ["users.id"], name=op.f("fk_ticket_collaborators_added_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_ticket_collaborators_ticket_id_tickets")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ticket_collaborators_user_id_users")
        ),
        sa.PrimaryKeyConstraint("ticket_id", "user_id", name=op.f("pk_ticket_collaborators")),
    )
    op.create_index(
        op.f("ix_ticket_collaborators_added_by_id"),
        "ticket_collaborators",
        ["added_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticket_collaborators_user_id"), "ticket_collaborators", ["user_id"], unique=False
    )
    op.create_table(
        "ticket_events",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "comment",
                "internal_note",
                "audit",
                name="ticket_event_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("public_detail", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_ticket_events_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_ticket_events_ticket_id_tickets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_events")),
    )
    op.create_index(op.f("ix_ticket_events_actor_id"), "ticket_events", ["actor_id"], unique=False)
    op.create_index(
        "ix_ticket_events_ticket_id_at", "ticket_events", ["ticket_id", "at"], unique=False
    )
    op.execute(IMMUTABLE_FUNCTION)
    op.execute(IMMUTABLE_TRIGGER)
    op.create_table(
        "email_outbox",
        sa.Column("notification_id", sa.Uuid(), nullable=True),
        sa.Column("to_address", sa.String(length=320), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                name="email_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_email_outbox_attempts_non_negative")),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_email_outbox_notification_id_notifications"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
    )
    op.create_index(
        op.f("ix_email_outbox_notification_id"), "email_outbox", ["notification_id"], unique=False
    )
    op.create_index(
        "ix_email_outbox_status_next_attempt_at",
        "email_outbox",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_email_outbox_status_next_attempt_at", table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_notification_id"), table_name="email_outbox")
    op.drop_table("email_outbox")
    op.execute("DROP TRIGGER ticket_events_immutable ON ticket_events")
    op.execute("DROP FUNCTION reject_ticket_event_change()")
    op.drop_index("ix_ticket_events_ticket_id_at", table_name="ticket_events")
    op.drop_index(op.f("ix_ticket_events_actor_id"), table_name="ticket_events")
    op.drop_table("ticket_events")
    op.drop_index(op.f("ix_ticket_collaborators_user_id"), table_name="ticket_collaborators")
    op.drop_index(op.f("ix_ticket_collaborators_added_by_id"), table_name="ticket_collaborators")
    op.drop_table("ticket_collaborators")
    op.drop_index(
        "ix_sla_timers_active_due_at",
        table_name="sla_timers",
        postgresql_where=sa.text("met_at IS NULL AND stopped_at IS NULL AND paused_at IS NULL"),
    )
    op.drop_table("sla_timers")
    op.drop_index(
        "uq_notifications_user_id_dedupe_key",
        table_name="notifications",
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.drop_index("ix_notifications_user_id_read_at_created_at", table_name="notifications")
    op.drop_index(op.f("ix_notifications_ticket_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("escalation_events")
    op.drop_index(op.f("ix_attachments_uploader_id"), table_name="attachments")
    op.drop_index(
        "ix_attachments_unlinked_created_at",
        table_name="attachments",
        postgresql_where=sa.text("ticket_id IS NULL"),
    )
    op.drop_index(op.f("ix_attachments_ticket_id"), table_name="attachments")
    op.drop_table("attachments")
    op.drop_index("ix_tickets_updated_at", table_name="tickets")
    op.drop_index(
        "ix_tickets_title_trgm",
        table_name="tickets",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_tickets_ticket_no_trgm",
        table_name="tickets",
        postgresql_using="gin",
        postgresql_ops={"ticket_no": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_tickets_sla_started_at"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_requester_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_owner_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_eta"), table_name="tickets")
    op.drop_index("ix_tickets_escalation_level_priority", table_name="tickets")
    op.drop_index("ix_tickets_department_id_status", table_name="tickets")
    op.drop_index(op.f("ix_tickets_category_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_assignee_id"), table_name="tickets")
    op.drop_table("tickets")
    op.drop_table("worker_heartbeat")
    op.drop_table("ticket_counters")
