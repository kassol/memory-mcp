"""console admin password and sessions

The console signs in with its own admin password and gets a session cookie, separate from
the access tokens agents use (docs/adr/0001). Only hashes are stored.

Revision ID: 0006_console_auth
Revises: 0005_console_settings
Create Date: 2026-10-31 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0006_console_auth"
down_revision = "0005_console_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row (id = 1) once a password is set; password_hash is an scrypt hash with its parameters.
    op.execute(
        """
        CREATE TABLE console_admin (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          password_hash TEXT NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        """
    )
    # bootstrap = 1: opened with the configuration-file token, may only set the password.
    op.execute(
        """
        CREATE TABLE console_sessions (
          token_hash TEXT PRIMARY KEY,
          bootstrap INTEGER NOT NULL DEFAULT 0,
          created_at TIMESTAMP NOT NULL,
          last_used_at TIMESTAMP NOT NULL,
          expires_at TIMESTAMP NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS console_sessions")
    op.execute("DROP TABLE IF EXISTS console_admin")
