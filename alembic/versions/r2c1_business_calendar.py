from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "r2c1_business_calendar"
down_revision: str | None = "r2b_saved_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKING_SECONDS = """
CREATE FUNCTION working_seconds(start_at timestamptz, end_at timestamptz)
RETURNS double precision
LANGUAGE sql
STABLE
AS $$
    WITH calendar AS (
        SELECT working_days, work_start, work_end
        FROM business_calendar
        WHERE id = 1
        UNION ALL
        SELECT ARRAY[1, 2, 3, 4, 5]::smallint[], time '09:00', time '18:00'
        WHERE NOT EXISTS (SELECT 1 FROM business_calendar WHERE id = 1)
    ),
    days AS (
        SELECT day::date AS day
        FROM generate_series(
            ((start_at AT TIME ZONE 'UTC') + interval '5 hours 30 minutes')::date,
            ((end_at AT TIME ZONE 'UTC') + interval '5 hours 30 minutes')::date,
            interval '1 day'
        ) AS series(day)
        WHERE end_at > start_at
    )
    SELECT coalesce(sum(greatest(0, extract(epoch FROM
        least(end_at, ((d.day + c.work_end) - interval '5:30') AT TIME ZONE 'UTC')
        - greatest(start_at, ((d.day + c.work_start) - interval '5:30') AT TIME ZONE 'UTC')
    ))), 0)::double precision
    FROM days AS d
    CROSS JOIN calendar AS c
    WHERE extract(isodow FROM d.day)::smallint = ANY(c.working_days)
      AND NOT EXISTS (
          SELECT 1 FROM holidays AS h WHERE h.holiday_date = d.day AND h.removed_at IS NULL
      )
$$
"""


def upgrade() -> None:
    op.create_table(
        "business_calendar",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("working_days", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("work_start", sa.Time(), nullable=False),
        sa.Column("work_end", sa.Time(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "cardinality(working_days) BETWEEN 1 AND 7",
            name=op.f("ck_business_calendar_working_days_count"),
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_business_calendar_single_row")),
        sa.CheckConstraint("work_start < work_end", name=op.f("ck_business_calendar_hours_order")),
        sa.CheckConstraint(
            "working_days <@ ARRAY[1,2,3,4,5,6,7]::smallint[]",
            name=op.f("ck_business_calendar_working_days_range"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["users.id"], name=op.f("fk_business_calendar_updated_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_calendar")),
    )
    op.create_index(
        op.f("ix_business_calendar_updated_by_id"),
        "business_calendar",
        ["updated_by_id"],
        unique=False,
    )
    op.create_table(
        "holidays",
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_by_id", sa.Uuid(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_holidays_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["removed_by_id"], ["users.id"], name=op.f("fk_holidays_removed_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holidays")),
    )
    op.create_index(op.f("ix_holidays_created_by_id"), "holidays", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_holidays_removed_by_id"), "holidays", ["removed_by_id"], unique=False)
    op.create_index(
        "uq_holidays_active_date",
        "holidays",
        ["holiday_date"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.add_column("categories", sa.Column("sla_mode", sa.String(length=32), nullable=True))
    op.create_check_constraint(
        "ck_categories_category_sla_mode",
        "categories",
        "sla_mode IN ('calendar', 'business')",
    )
    op.add_column("departments", sa.Column("sla_mode", sa.String(length=32), nullable=True))
    op.create_check_constraint(
        "ck_departments_department_sla_mode",
        "departments",
        "sla_mode IN ('calendar', 'business')",
    )
    op.execute(WORKING_SECONDS)


def downgrade() -> None:
    op.execute("DROP FUNCTION working_seconds(timestamptz, timestamptz)")
    op.drop_constraint("ck_departments_department_sla_mode", "departments", type_="check")
    op.drop_column("departments", "sla_mode")
    op.drop_constraint("ck_categories_category_sla_mode", "categories", type_="check")
    op.drop_column("categories", "sla_mode")
    op.drop_index(
        "uq_holidays_active_date",
        table_name="holidays",
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.drop_index(op.f("ix_holidays_removed_by_id"), table_name="holidays")
    op.drop_index(op.f("ix_holidays_created_by_id"), table_name="holidays")
    op.drop_table("holidays")
    op.drop_index(op.f("ix_business_calendar_updated_by_id"), table_name="business_calendar")
    op.drop_table("business_calendar")
