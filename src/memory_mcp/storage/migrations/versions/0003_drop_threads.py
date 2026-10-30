"""drop threads, thread_messages and memories thread provenance columns

Nothing writes threads or thread_messages, and memories.source_thread_id /
source_refs were never filled. SQLite cannot drop a column that carries a
foreign key, so memories is rebuilt with the 12-step procedure from
https://www.sqlite.org/lang_altertable.html#otheralter

Revision ID: 0003_drop_threads
Revises: 0002_drop_working_memory_cache
Create Date: 2026-10-30 00:00:00.000000

"""
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "0003_drop_threads"
down_revision = "0002_drop_working_memory_cache"
branch_labels = None
depends_on = None


# memories columns shared by revisions 0002 and 0003.
_SHARED_COLUMNS = (
    "id, entity_key, entity_type, content, content_tokens, title, title_tokens, "
    "parent_id, mutation_type, mutation_reason, created_at, valid_from, valid_until, "
    "is_current, confidence, review_status, archived_reason, archived_at, conflict, "
    "conflict_with_id, tags, source, origin_client, origin_session_id, "
    "access_count, last_accessed_at, reinforce_count"
)


def _memories_table(name: str, with_threads: bool) -> str:
    thread_columns = (
        """
          source_thread_id TEXT REFERENCES threads(thread_id) ON DELETE SET NULL,
          source_refs TEXT,
"""
        if with_threads
        else ""
    )
    return f"""
        CREATE TABLE {name} (
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
{thread_columns}
          access_count INTEGER NOT NULL DEFAULT 0,
          last_accessed_at TIMESTAMP,
          reinforce_count INTEGER NOT NULL DEFAULT 0
        )
        """


_MEMORIES_INDEXES = (
    "CREATE INDEX idx_memories_entity_key ON memories(entity_key)",
    "CREATE INDEX idx_memories_entity_type ON memories(entity_type)",
    "CREATE INDEX idx_memories_current ON memories(is_current) WHERE is_current = 1",
    "CREATE INDEX idx_memories_review_status ON memories(review_status)",
    "CREATE INDEX idx_memories_origin_client ON memories(origin_client)",
    "CREATE INDEX idx_memories_created_at ON memories(created_at DESC)",
    "CREATE INDEX idx_memories_last_accessed_at ON memories(last_accessed_at DESC)",
)

_MEMORIES_FTS_TRIGGERS = (
    """
    CREATE TRIGGER memories_fts_ai AFTER INSERT ON memories BEGIN
      INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
      VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
    END
    """,
    """
    CREATE TRIGGER memories_fts_ad AFTER DELETE ON memories BEGIN
      INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
      VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
    END
    """,
    """
    CREATE TRIGGER memories_fts_au AFTER UPDATE ON memories BEGIN
      INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
      VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
      INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
      VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
    END
    """,
)

_THREAD_OBJECTS = (
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
    """,
    "CREATE INDEX idx_threads_provider ON threads(source_provider)",
    "CREATE INDEX idx_threads_started_at ON threads(started_at DESC)",
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
    """,
    "CREATE INDEX idx_thread_messages_thread_id ON thread_messages(thread_id, seq)",
    """
    CREATE VIRTUAL TABLE thread_messages_fts USING fts5(
      content,
      role UNINDEXED,
      content='thread_messages',
      content_rowid='rowid',
      tokenize='unicode61 remove_diacritics 2'
    )
    """,
    """
    CREATE TRIGGER thread_messages_fts_ai AFTER INSERT ON thread_messages BEGIN
      INSERT INTO thread_messages_fts(rowid, content, role)
      VALUES (new.rowid, new.content, new.role);
    END
    """,
    """
    CREATE TRIGGER thread_messages_fts_ad AFTER DELETE ON thread_messages BEGIN
      INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
      VALUES('delete', old.rowid, old.content, old.role);
    END
    """,
    """
    CREATE TRIGGER thread_messages_fts_au AFTER UPDATE ON thread_messages BEGIN
      INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
      VALUES('delete', old.rowid, old.content, old.role);
      INSERT INTO thread_messages_fts(rowid, content, role)
      VALUES (new.rowid, new.content, new.role);
    END
    """,
)

_DROP_THREAD_OBJECTS = (
    "DROP TRIGGER IF EXISTS thread_messages_fts_au",
    "DROP TRIGGER IF EXISTS thread_messages_fts_ad",
    "DROP TRIGGER IF EXISTS thread_messages_fts_ai",
    "DROP TABLE IF EXISTS thread_messages_fts",
    "DROP INDEX IF EXISTS idx_thread_messages_thread_id",
    "DROP TABLE IF EXISTS thread_messages",
    "DROP INDEX IF EXISTS idx_threads_started_at",
    "DROP INDEX IF EXISTS idx_threads_provider",
    "DROP TABLE IF EXISTS threads",
)


def _rebuild(with_threads: bool, before: tuple[str, ...]) -> None:
    """Rebuild memories with or without the thread columns, keeping every rowid.

    memories_fts is external content keyed by rowid, so rowids must survive the copy.
    PRAGMA foreign_keys is a no-op inside a transaction, and SQLite's alembic impl
    has transactional_ddl = False but pysqlite still opens an implicit transaction
    on the first DML. Run in an autocommit block and manage BEGIN/COMMIT here.
    """
    statements = (
        *before,
        _memories_table("memories_new", with_threads),
        f"INSERT INTO memories_new(rowid, {_SHARED_COLUMNS}) "
        f"SELECT rowid, {_SHARED_COLUMNS} FROM memories",
        "DROP TABLE memories",
        "ALTER TABLE memories_new RENAME TO memories",
        *_MEMORIES_INDEXES,
        *(
            ("CREATE INDEX idx_memories_source_thread_id ON memories(source_thread_id)",)
            if with_threads
            else ()
        ),
        *_MEMORIES_FTS_TRIGGERS,
        "INSERT INTO memories_fts(memories_fts) VALUES('rebuild')",
    )
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        # The copy lists columns explicitly; any column it does not name would be lost silently.
        actual = {row[1] for row in conn.execute(text("PRAGMA table_info(memories)")).fetchall()}
        expected = {c.strip() for c in _SHARED_COLUMNS.split(",")}
        expected |= set() if with_threads else {"source_thread_id", "source_refs"}
        if actual != expected:
            raise RuntimeError(
                f"memories columns differ from what 0003 copies; refusing to rebuild. "
                f"unexpected={sorted(actual - expected)} missing={sorted(expected - actual)}"
            )
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        try:
            conn.execute(text("BEGIN"))
            try:
                for sql in statements:
                    conn.execute(text(sql))
                violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
                if violations:
                    raise RuntimeError(f"foreign_key_check failed: {violations[:20]}")
                conn.execute(text("COMMIT"))
            except BaseException:
                conn.execute(text("ROLLBACK"))
                raise
        finally:
            conn.execute(text("PRAGMA foreign_keys = ON"))


def upgrade() -> None:
    _rebuild(with_threads=False, before=_DROP_THREAD_OBJECTS)


def downgrade() -> None:
    _rebuild(with_threads=True, before=_THREAD_OBJECTS)
