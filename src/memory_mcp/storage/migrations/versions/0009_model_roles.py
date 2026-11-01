"""model roles: a provider, model and timeout per kind of model call

Each kind of call picks its own provider, model and timeout (issue #13): write (key assignment,
merge and the conflict judgment inside `remember`) and maintenance (the background checks'
judgments). A role without a row uses what the service had before roles existed: the
configuration-file provider, `llm_model` and a 30 second timeout.

The embedding role is read-only: stored vectors were computed with it, so it always follows the
configuration file (docs/adr/0002).

Revision ID: 0009_model_roles
Revises: 0008_providers
Create Date: 2026-11-01 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0009_model_roles"
down_revision = "0008_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE model_roles (
          role TEXT PRIMARY KEY,
          provider_id TEXT NOT NULL REFERENCES providers(id),
          model TEXT NOT NULL,
          timeout REAL NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_roles")
