from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r2a_kpi_indexes"
down_revision: str | None = "b05_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_escalation_events_at", "escalation_events", ["at"], unique=False)
    op.create_index(
        "ix_ticket_events_kpi_actions",
        "ticket_events",
        ["action", "at", "ticket_id"],
        unique=False,
        postgresql_where=sa.text("action IN ('acknowledged', 'resolved', 'reopened')"),
    )
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tickets_created_at", table_name="tickets")
    op.drop_index(
        "ix_ticket_events_kpi_actions",
        table_name="ticket_events",
        postgresql_where=sa.text("action IN ('acknowledged', 'resolved', 'reopened')"),
    )
    op.drop_index("ix_escalation_events_at", table_name="escalation_events")
