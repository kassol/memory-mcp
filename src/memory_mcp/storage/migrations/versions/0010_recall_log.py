"""recall log and daily statistics

A recall is the unit that tells whether retrieval works: what was asked, how long it took, what came
back (issue #15). `recall_log` keeps that for 30 days and can be switched off. `daily_events` counts
writes and recalls per day and access token and keeps each recall's latency, so the median stays
exact; it is kept 90 days and does not depend on the log setting.

Revision ID: 0010_recall_log
Revises: 0009_model_roles
Create Date: 2026-11-01 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0010_recall_log"
down_revision = "0009_model_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE recall_log (
          id TEXT PRIMARY KEY,
          at TIMESTAMP NOT NULL,
          token TEXT,
          query TEXT NOT NULL,
          latency_ms REAL NOT NULL,
          results INTEGER NOT NULL,
          memory_ids TEXT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_recall_log_at ON recall_log(at)")
    op.execute(
        """
        CREATE TABLE daily_events (
          id INTEGER PRIMARY KEY,
          day TEXT NOT NULL,
          token TEXT NOT NULL,
          kind TEXT NOT NULL,
          latency_ms REAL
        )
        """
    )
    op.execute("CREATE INDEX idx_daily_events_day ON daily_events(day)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_events")
    op.execute("DROP TABLE IF EXISTS recall_log")
