"""named access tokens and the writing token on memories

Clients get named, revocable access tokens (issue #11). Only the SHA-256 of a token is stored.
The configuration-file token is the row with id 'initial': it has no hash (its value stays in the
configuration file) and is disabled by setting revoked_at. memories.origin_token records the name
of the token that wrote a version.

Revision ID: 0007_access_tokens
Revises: 0006_console_auth
Create Date: 2026-11-01 00:00:00.000000

"""
from datetime import datetime, timezone

from alembic import op


# revision identifiers, used by Alembic.
revision = "0007_access_tokens"
down_revision = "0006_console_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE access_tokens (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          token_hash TEXT UNIQUE,
          source TEXT NOT NULL,
          created_at TIMESTAMP NOT NULL,
          last_used_at TIMESTAMP,
          revoked_at TIMESTAMP
        )
        """
    )
    now = datetime.now(timezone.utc).isoformat()
    op.execute(
        "INSERT INTO access_tokens (id, name, token_hash, source, created_at) "
        f"VALUES ('initial', 'initial', NULL, 'file', '{now}')"
    )
    op.execute("ALTER TABLE memories ADD COLUMN origin_token TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP COLUMN origin_token")
    op.execute("DROP TABLE IF EXISTS access_tokens")
