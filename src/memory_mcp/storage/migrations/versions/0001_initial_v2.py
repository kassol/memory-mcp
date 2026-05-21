"""initial v2 schema

Revision ID: 0001_initial_v2
Revises:
Create Date: 2026-05-21 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0001_initial_v2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("PRAGMA foreign_keys = ON")

    # entities
    op.execute(
        """
        CREATE TABLE entities (
          entity_key TEXT PRIMARY KEY,
          name TEXT,
          entity_type TEXT NOT NULL,
          current_memory_id TEXT,
          created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_entities_entity_type ON entities(entity_type)")

    # threads (created before memories for FK)
    op.execute(
        """
        CREATE TABLE threads (
          thread_id TEXT PRIMARY KEY,
          source_provider TEXT NOT NULL,
          source_ref TEXT,
          title TEXT,
          started_at TIMESTAMP,
          ended_at TIMESTAMP,
          message_count INTEGER NOT NULL DEFAULT 0,
          summary TEXT,
          metadata TEXT,
          last_synced_mtime INTEGER,
          last_synced_seq INTEGER,
          created_at TIMESTAMP NOT NULL,
          imported_at TIMESTAMP NOT NULL,
          UNIQUE(source_provider, source_ref)
        )
        """
    )
    op.execute("CREATE INDEX idx_threads_provider ON threads(source_provider)")
    op.execute("CREATE INDEX idx_threads_started_at ON threads(started_at DESC)")

    op.execute(
        """
        CREATE TABLE thread_messages (
          message_id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
          seq INTEGER NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          ts TIMESTAMP,
          metadata TEXT,
          UNIQUE(thread_id, seq)
        )
        """
    )
    op.execute("CREATE INDEX idx_thread_messages_thread_id ON thread_messages(thread_id, seq)")

    op.execute(
        """
        CREATE VIRTUAL TABLE thread_messages_fts USING fts5(
          content,
          role UNINDEXED,
          content='thread_messages',
          content_rowid='rowid',
          tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER thread_messages_fts_ai AFTER INSERT ON thread_messages BEGIN
          INSERT INTO thread_messages_fts(rowid, content, role)
          VALUES (new.rowid, new.content, new.role);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER thread_messages_fts_ad AFTER DELETE ON thread_messages BEGIN
          INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
          VALUES('delete', old.rowid, old.content, old.role);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER thread_messages_fts_au AFTER UPDATE ON thread_messages BEGIN
          INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
          VALUES('delete', old.rowid, old.content, old.role);
          INSERT INTO thread_messages_fts(rowid, content, role)
          VALUES (new.rowid, new.content, new.role);
        END
        """
    )

    # memories
    op.execute(
        """
        CREATE TABLE memories (
          id TEXT PRIMARY KEY,
          entity_key TEXT NOT NULL,
          entity_type TEXT NOT NULL,

          content TEXT NOT NULL,
          content_tokens TEXT,
          title TEXT,
          title_tokens TEXT,

          parent_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
          mutation_type TEXT NOT NULL,
          mutation_reason TEXT,

          created_at TIMESTAMP NOT NULL,
          valid_from TIMESTAMP NOT NULL,
          valid_until TIMESTAMP,

          is_current BOOLEAN NOT NULL DEFAULT 1,
          confidence REAL NOT NULL DEFAULT 1.0,
          review_status TEXT NOT NULL DEFAULT 'auto',
          archived_reason TEXT,
          archived_at TIMESTAMP,
          conflict BOOLEAN NOT NULL DEFAULT 0,
          conflict_with_id TEXT REFERENCES memories(id) ON DELETE SET NULL,

          tags TEXT,
          source TEXT NOT NULL DEFAULT 'conversation',
          origin_client TEXT,
          origin_session_id TEXT,

          source_thread_id TEXT REFERENCES threads(thread_id) ON DELETE SET NULL,
          source_refs TEXT,

          access_count INTEGER NOT NULL DEFAULT 0,
          last_accessed_at TIMESTAMP,
          reinforce_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX idx_memories_entity_key ON memories(entity_key)")
    op.execute("CREATE INDEX idx_memories_entity_type ON memories(entity_type)")
    op.execute("CREATE INDEX idx_memories_current ON memories(is_current) WHERE is_current = 1")
    op.execute("CREATE INDEX idx_memories_review_status ON memories(review_status)")
    op.execute("CREATE INDEX idx_memories_origin_client ON memories(origin_client)")
    op.execute("CREATE INDEX idx_memories_source_thread_id ON memories(source_thread_id)")
    op.execute("CREATE INDEX idx_memories_created_at ON memories(created_at DESC)")
    op.execute("CREATE INDEX idx_memories_last_accessed_at ON memories(last_accessed_at DESC)")

    op.execute(
        """
        CREATE VIRTUAL TABLE memories_fts USING fts5(
          content_tokens,
          title_tokens,
          entity_key UNINDEXED,
          content='memories',
          content_rowid='rowid',
          tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER memories_fts_ai AFTER INSERT ON memories BEGIN
          INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
          VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER memories_fts_ad AFTER DELETE ON memories BEGIN
          INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
          VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER memories_fts_au AFTER UPDATE ON memories BEGIN
          INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
          VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
          INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
          VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
        END
        """
    )

    # relations
    op.execute(
        """
        CREATE TABLE relations (
          id TEXT PRIMARY KEY,
          from_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
          to_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
          relation_type TEXT NOT NULL,
          properties TEXT,
          created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_relations_from ON relations(from_entity_key)")
    op.execute("CREATE INDEX idx_relations_to ON relations(to_entity_key)")
    op.execute("CREATE INDEX idx_relations_type ON relations(relation_type)")

    # jobs
    op.execute(
        """
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY,
          job_type TEXT NOT NULL,
          payload TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 3,
          scheduled_at TIMESTAMP NOT NULL,
          started_at TIMESTAMP,
          finished_at TIMESTAMP,
          next_retry_at TIMESTAMP,
          error TEXT,
          created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_jobs_pending ON jobs(scheduled_at) WHERE status = 'pending'")
    op.execute(
        "CREATE INDEX idx_jobs_retry ON jobs(next_retry_at) "
        "WHERE status = 'pending' AND next_retry_at IS NOT NULL"
    )

    # working_memory_cache
    op.execute(
        """
        CREATE TABLE working_memory_cache (
          cache_key TEXT PRIMARY KEY,
          content TEXT NOT NULL,
          generated_at TIMESTAMP NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS working_memory_cache")
    op.execute("DROP INDEX IF EXISTS idx_jobs_retry")
    op.execute("DROP INDEX IF EXISTS idx_jobs_pending")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP INDEX IF EXISTS idx_relations_type")
    op.execute("DROP INDEX IF EXISTS idx_relations_to")
    op.execute("DROP INDEX IF EXISTS idx_relations_from")
    op.execute("DROP TABLE IF EXISTS relations")
    op.execute("DROP TRIGGER IF EXISTS memories_fts_au")
    op.execute("DROP TRIGGER IF EXISTS memories_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS memories_fts_ai")
    op.execute("DROP TABLE IF EXISTS memories_fts")
    op.execute("DROP INDEX IF EXISTS idx_memories_last_accessed_at")
    op.execute("DROP INDEX IF EXISTS idx_memories_created_at")
    op.execute("DROP INDEX IF EXISTS idx_memories_source_thread_id")
    op.execute("DROP INDEX IF EXISTS idx_memories_origin_client")
    op.execute("DROP INDEX IF EXISTS idx_memories_review_status")
    op.execute("DROP INDEX IF EXISTS idx_memories_current")
    op.execute("DROP INDEX IF EXISTS idx_memories_entity_type")
    op.execute("DROP INDEX IF EXISTS idx_memories_entity_key")
    op.execute("DROP TABLE IF EXISTS memories")
    op.execute("DROP TRIGGER IF EXISTS thread_messages_fts_au")
    op.execute("DROP TRIGGER IF EXISTS thread_messages_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS thread_messages_fts_ai")
    op.execute("DROP TABLE IF EXISTS thread_messages_fts")
    op.execute("DROP INDEX IF EXISTS idx_thread_messages_thread_id")
    op.execute("DROP TABLE IF EXISTS thread_messages")
    op.execute("DROP INDEX IF EXISTS idx_threads_started_at")
    op.execute("DROP INDEX IF EXISTS idx_threads_provider")
    op.execute("DROP TABLE IF EXISTS threads")
    op.execute("DROP INDEX IF EXISTS idx_entities_entity_type")
    op.execute("DROP TABLE IF EXISTS entities")
