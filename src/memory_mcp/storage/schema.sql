-- memory-mcp v2 schema reference at head 0010_recall_log (authoritative version: alembic versions/)

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

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

  access_count INTEGER NOT NULL DEFAULT 0,
  last_accessed_at TIMESTAMP,
  reinforce_count INTEGER NOT NULL DEFAULT 0,
  -- name of the access token that wrote this version (0007)
  origin_token TEXT
);
CREATE INDEX idx_memories_entity_key ON memories(entity_key);
CREATE INDEX idx_memories_entity_type ON memories(entity_type);
CREATE INDEX idx_memories_current ON memories(is_current) WHERE is_current = 1;
CREATE INDEX idx_memories_review_status ON memories(review_status);
CREATE INDEX idx_memories_origin_client ON memories(origin_client);
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
-- entities (created after memories so current_memory_id can FK to memories)
-- ---------------------------------------------------------------------------
CREATE TABLE entities (
  entity_key TEXT PRIMARY KEY,
  name TEXT,
  entity_type TEXT NOT NULL,
  current_memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_entities_entity_type ON entities(entity_type);

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
-- jobs (one row per maintenance run, job_type = 'maintenance')
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
-- maintenance findings (need review) and checks (already judged; see GLOSSARY.md)
-- ---------------------------------------------------------------------------
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
);
CREATE INDEX idx_memory_findings_status ON memory_findings(status, kind);

-- subject: one memory id (internal, neighbours) or "<id>|<id>" sorted (pair)
CREATE TABLE memory_checks (
  check_type TEXT NOT NULL,
  subject TEXT NOT NULL,
  outcome TEXT NOT NULL,
  checked_at TIMESTAMP NOT NULL,
  PRIMARY KEY (check_type, subject)
);

-- ---------------------------------------------------------------------------
-- runtime settings saved in the console (value is JSON); see settings_registry.py
-- ---------------------------------------------------------------------------
CREATE TABLE console_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

-- ---------------------------------------------------------------------------
-- console sign-in (docs/adr/0001): admin password hash and session hashes
-- ---------------------------------------------------------------------------
CREATE TABLE console_admin (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  password_hash TEXT NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE console_sessions (
  token_hash TEXT PRIMARY KEY,
  bootstrap INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL,
  last_used_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL
);

-- ---------------------------------------------------------------------------
-- named access tokens (issue #11): only hashes are stored; id 'initial' is the
-- configuration-file token, whose hash startup stores once (NULL until then)
-- ---------------------------------------------------------------------------
CREATE TABLE access_tokens (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  token_hash TEXT UNIQUE,
  source TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  last_used_at TIMESTAMP,
  revoked_at TIMESTAMP
);
INSERT INTO access_tokens (id, name, token_hash, source, created_at)
  VALUES ('initial', 'initial', NULL, 'file', CURRENT_TIMESTAMP);

-- ---------------------------------------------------------------------------
-- model providers (issue #12): API keys are stored as AES-GCM ciphertext only;
-- id 'file' is the configuration-file provider, whose NULL address and key mean
-- "use the configuration file"
-- ---------------------------------------------------------------------------
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
);
INSERT INTO providers (id, name, protocol, base_url, api_key_cipher, source, created_at, updated_at)
  VALUES ('file', 'openrouter', 'openai', NULL, NULL, 'file', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- ---------------------------------------------------------------------------
-- model roles (issue #13): which provider, model and timeout each role uses;
-- a missing row means the configuration-file provider and llm_model
-- ---------------------------------------------------------------------------
CREATE TABLE model_roles (
  role TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(id),
  model TEXT NOT NULL,
  timeout REAL NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

-- ---------------------------------------------------------------------------
-- recall log and daily statistics (issue #15): the log keeps query, token,
-- latency and top memory ids for 30 days; daily_events counts writes and
-- recalls per day and token for 90 days, whatever the log setting says
-- ---------------------------------------------------------------------------
CREATE TABLE recall_log (
  id TEXT PRIMARY KEY,
  at TIMESTAMP NOT NULL,
  token TEXT,
  query TEXT NOT NULL,
  latency_ms REAL NOT NULL,
  results INTEGER NOT NULL,
  memory_ids TEXT NOT NULL
);
CREATE INDEX idx_recall_log_at ON recall_log(at);

CREATE TABLE daily_events (
  id INTEGER PRIMARY KEY,
  day TEXT NOT NULL,
  token TEXT NOT NULL,
  kind TEXT NOT NULL,
  latency_ms REAL
);
CREATE INDEX idx_daily_events_day ON daily_events(day);
