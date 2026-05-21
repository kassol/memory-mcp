-- memory-mcp v2 schema reference (authoritative version: alembic versions/0001_initial_v2.py)
-- Spec: docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md §4

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

-- ---------------------------------------------------------------------------
-- entities
-- ---------------------------------------------------------------------------
CREATE TABLE entities (
  entity_key TEXT PRIMARY KEY,
  name TEXT,
  entity_type TEXT NOT NULL,
  current_memory_id TEXT,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_entities_entity_type ON entities(entity_type);

-- ---------------------------------------------------------------------------
-- threads (created early so memories.source_thread_id FK is satisfied)
-- ---------------------------------------------------------------------------
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
);
CREATE INDEX idx_threads_provider ON threads(source_provider);
CREATE INDEX idx_threads_started_at ON threads(started_at DESC);

CREATE TABLE thread_messages (
  message_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TIMESTAMP,
  metadata TEXT,
  UNIQUE(thread_id, seq)
);
CREATE INDEX idx_thread_messages_thread_id ON thread_messages(thread_id, seq);

CREATE VIRTUAL TABLE thread_messages_fts USING fts5(
  content,
  role UNINDEXED,
  content='thread_messages',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER thread_messages_fts_ai AFTER INSERT ON thread_messages BEGIN
  INSERT INTO thread_messages_fts(rowid, content, role)
  VALUES (new.rowid, new.content, new.role);
END;
CREATE TRIGGER thread_messages_fts_ad AFTER DELETE ON thread_messages BEGIN
  INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
  VALUES('delete', old.rowid, old.content, old.role);
END;
CREATE TRIGGER thread_messages_fts_au AFTER UPDATE ON thread_messages BEGIN
  INSERT INTO thread_messages_fts(thread_messages_fts, rowid, content, role)
  VALUES('delete', old.rowid, old.content, old.role);
  INSERT INTO thread_messages_fts(rowid, content, role)
  VALUES (new.rowid, new.content, new.role);
END;

-- ---------------------------------------------------------------------------
-- memories (main v2 table)
-- ---------------------------------------------------------------------------
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
);
CREATE INDEX idx_memories_entity_key ON memories(entity_key);
CREATE INDEX idx_memories_entity_type ON memories(entity_type);
CREATE INDEX idx_memories_current ON memories(is_current) WHERE is_current = 1;
CREATE INDEX idx_memories_review_status ON memories(review_status);
CREATE INDEX idx_memories_origin_client ON memories(origin_client);
CREATE INDEX idx_memories_source_thread_id ON memories(source_thread_id);
CREATE INDEX idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX idx_memories_last_accessed_at ON memories(last_accessed_at DESC);

CREATE VIRTUAL TABLE memories_fts USING fts5(
  content_tokens,
  title_tokens,
  entity_key UNINDEXED,
  content='memories',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER memories_fts_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
  VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
END;
CREATE TRIGGER memories_fts_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
  VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
END;
CREATE TRIGGER memories_fts_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content_tokens, title_tokens, entity_key)
  VALUES('delete', old.rowid, old.content_tokens, old.title_tokens, old.entity_key);
  INSERT INTO memories_fts(rowid, content_tokens, title_tokens, entity_key)
  VALUES (new.rowid, new.content_tokens, new.title_tokens, new.entity_key);
END;

-- ---------------------------------------------------------------------------
-- relations
-- ---------------------------------------------------------------------------
CREATE TABLE relations (
  id TEXT PRIMARY KEY,
  from_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
  to_entity_key TEXT NOT NULL REFERENCES entities(entity_key) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  properties TEXT,
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_relations_from ON relations(from_entity_key);
CREATE INDEX idx_relations_to ON relations(to_entity_key);
CREATE INDEX idx_relations_type ON relations(relation_type);

-- ---------------------------------------------------------------------------
-- jobs (worker queue, M4 will use)
-- ---------------------------------------------------------------------------
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
);
CREATE INDEX idx_jobs_pending ON jobs(scheduled_at) WHERE status = 'pending';
CREATE INDEX idx_jobs_retry ON jobs(next_retry_at)
  WHERE status = 'pending' AND next_retry_at IS NOT NULL;

-- ---------------------------------------------------------------------------
-- working_memory_cache (briefing cache, M4 will use)
-- ---------------------------------------------------------------------------
CREATE TABLE working_memory_cache (
  cache_key TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  generated_at TIMESTAMP NOT NULL
);
