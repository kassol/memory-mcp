"""maintenance findings and checks

Findings are conclusions a person must review; checks record what was already judged
(including compatible results) so the same subject is never judged twice. See GLOSSARY.md.

Revision ID: 0004_maintenance_findings
Revises: 0003_drop_threads
Create Date: 2026-10-30 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0004_maintenance_findings"
down_revision = "0003_drop_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE memory_findings (
          id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          memory_id TEXT NOT NULL,
          other_memory_id TEXT,
          entity_key TEXT,
          detail TEXT,
          status TEXT NOT NULL DEFAULT 'open',
          created_at TIMESTAMP NOT NULL,
          resolved_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX idx_memory_findings_status ON memory_findings(status, kind)")
    # subject: one memory id (internal, neighbour scan) or "<id>|<id>" sorted (pair)
    op.execute(
        """
        CREATE TABLE memory_checks (
          check_type TEXT NOT NULL,
          subject TEXT NOT NULL,
          outcome TEXT NOT NULL,
          checked_at TIMESTAMP NOT NULL,
          PRIMARY KEY (check_type, subject)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_checks")
    op.execute("DROP INDEX IF EXISTS idx_memory_findings_status")
    op.execute("DROP TABLE IF EXISTS memory_findings")
