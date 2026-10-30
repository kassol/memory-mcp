"""drop working_memory_cache

The Working Memory briefing was removed; nothing reads or writes this table.

Revision ID: 0002_drop_working_memory_cache
Revises: 0001_initial_v2
Create Date: 2026-10-30 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0002_drop_working_memory_cache"
down_revision = "0001_initial_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS working_memory_cache")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE working_memory_cache (
          cache_key TEXT PRIMARY KEY,
          content TEXT NOT NULL,
          generated_at TIMESTAMP NOT NULL
        )
        """
    )
