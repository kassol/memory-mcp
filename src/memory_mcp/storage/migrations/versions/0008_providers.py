"""model providers with encrypted API keys

Providers become managed records (issue #12): name, protocol, base URL and API key. Only the
ciphertext of a key is stored; the data key lives in a file under the data directory. The
configuration-file OpenRouter settings appear as the row with id 'file', whose NULL base URL and
key columns mean "use the configuration file" and can be overridden and reverted. Last call status
is recorded per provider so a failing one is visible in the console.

Revision ID: 0008_providers
Revises: 0007_access_tokens
Create Date: 2026-11-01 00:00:00.000000

"""
from datetime import datetime, timezone

from alembic import op


# revision identifiers, used by Alembic.
revision = "0008_providers"
down_revision = "0007_access_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE providers (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          protocol TEXT NOT NULL,
          base_url TEXT,
          api_key_cipher TEXT,
          source TEXT NOT NULL,
          created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL,
          last_call_at TIMESTAMP,
          last_call_ok INTEGER,
          last_call_error TEXT
        )
        """
    )
    now = datetime.now(timezone.utc).isoformat()
    op.execute(
        "INSERT INTO providers (id, name, protocol, base_url, api_key_cipher, source, created_at, updated_at) "
        f"VALUES ('file', 'openrouter', 'openai', NULL, NULL, 'file', '{now}', '{now}')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS providers")
