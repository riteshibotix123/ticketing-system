from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r2c2_notification_preferences"
down_revision: str | None = "r2c1_business_calendar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_digests",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notification_digests_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_digests")),
        sa.UniqueConstraint(
            "user_id", "digest_date", name=op.f("uq_notification_digests_user_id_digest_date")
        ),
    )
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "non_critical_email",
            sa.Enum(
                "immediate",
                "daily_digest",
                "off",
                name="non_critical_email",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("digest_hour", sa.SmallInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "digest_hour BETWEEN 0 AND 23",
            name=op.f("ck_notification_preferences_digest_hour_range"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notification_preferences_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_notification_preferences")),
    )
    op.create_table(
        "digest_items",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("digest_id", sa.Uuid(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dropped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["digest_id"],
            ["notification_digests.id"],
            name=op.f("fk_digest_items_digest_id_notification_digests"),
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_digest_items_notification_id_notifications"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_digest_items_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_digest_items")),
        sa.UniqueConstraint("notification_id", name=op.f("uq_digest_items_notification_id")),
    )
    op.create_index(op.f("ix_digest_items_digest_id"), "digest_items", ["digest_id"], unique=False)
    op.create_index(
        "ix_digest_items_pending",
        "digest_items",
        ["user_id", "queued_at"],
        unique=False,
        postgresql_where=sa.text("sent_at IS NULL AND dropped_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_digest_items_pending",
        table_name="digest_items",
        postgresql_where=sa.text("sent_at IS NULL AND dropped_at IS NULL"),
    )
    op.drop_index(op.f("ix_digest_items_digest_id"), table_name="digest_items")
    op.drop_table("digest_items")
    op.drop_table("notification_preferences")
    op.drop_table("notification_digests")
