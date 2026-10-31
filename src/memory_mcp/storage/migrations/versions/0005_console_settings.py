"""console settings

Runtime settings saved in the console; they take precedence over the configuration file.
See docs/adr/0002 and memory_mcp/settings_registry.py.

Revision ID: 0005_console_settings
Revises: 0004_maintenance_findings
Create Date: 2026-10-31 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0005_console_settings"
down_revision = "0004_maintenance_findings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # value: the setting value as JSON
    op.execute(
        """
        CREATE TABLE console_settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS console_settings")
