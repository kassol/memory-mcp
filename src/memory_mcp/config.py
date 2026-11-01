import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

# Startup settings are read before this module's settings object exists, so they live in a JSON file
# under the data directory instead of SQLite (docs/adr/0002). A console change writes a draft, checks
# it, then applies it as this file; see startup.py.
STARTUP_KEYS = ("port", "data_dir", "vector_backend", "embedding_model", "embedding_dim", "debug")
OVERRIDE_FILE = "startup-settings.json"
PENDING_FILE = "startup-settings.pending.json"
APPLY_FILE = "startup-apply.json"


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8765
    debug: bool = False

    # Auth
    auth_token: str

    # Storage
    data_dir: str = "./data"
    vector_backend: str = "lancedb"
    auto_migrate: bool = True  # FastAPI lifespan startup runs alembic upgrade head when True

    # Embedding
    openrouter_api_key: str = Field(
        validation_alias=AliasChoices("MEMORY_MCP_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("MEMORY_MCP_OPENROUTER_BASE_URL", "OPENROUTER_BASE_URL"),
    )
    embedding_model: str = Field(
        default="openai/text-embedding-3-small",
        validation_alias=AliasChoices("MEMORY_MCP_EMBEDDING_MODEL", "EMBEDDING_MODEL"),
    )
    embedding_dim: int = Field(
        default=1536,
        validation_alias=AliasChoices("MEMORY_MCP_EMBEDDING_DIM", "EMBEDDING_DIM"),
    )

    # Conflict Detection
    llm_model: str = Field(
        default="anthropic/claude-3-haiku",
        validation_alias=AliasChoices("MEMORY_MCP_LLM_MODEL", "LLM_MODEL"),
    )

    # Runtime settings from the configuration file. None means unset: the console value or the
    # code default in settings_registry applies. Read them through settings_registry.get().
    similarity_threshold: Optional[float] = None
    maintenance_max_llm_calls: Optional[int] = None
    recall_log_enabled: Optional[bool] = None
    fts_weight: Optional[float] = None
    rrf_k: Optional[int] = None
    candidates_per_source: Optional[int] = None
    graph_seeds: Optional[int] = None
    decay_lambda: Optional[float] = None
    cross_key_min_cosine: Optional[float] = None
    cross_key_neighbours: Optional[int] = None

    # Tokenizer
    jieba_user_dict_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MEMORY_MCP_JIEBA_USER_DICT", "JIEBA_USER_DICT"),
    )

    class Config:
        env_prefix = "MEMORY_MCP_"
        env_file = ".env"
        extra = "ignore"

    @property
    def sqlite_path(self) -> str:
        return os.path.join(self.data_dir, "memory.sqlite3")

    @property
    def vectors_dir(self) -> str:
        return os.path.join(self.data_dir, "vectors")

    @property
    def alembic_url(self) -> str:
        # alembic uses sync driver for migrations
        abs_path = Path(self.sqlite_path).resolve()
        return f"sqlite:///{abs_path}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    """A JSON object, or an empty dict; a broken or missing file must not stop the service."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: dict) -> None:
    """Write atomically, so a crash mid-write cannot leave a half-read file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def _startup_values(data: object) -> dict:
    if not isinstance(data, dict):
        return {}
    return {key: data[key] for key in STARTUP_KEYS if key in data}


def recover_startup(data_dir: str) -> dict:
    """The override file's values, after recovering from an apply that never became healthy.

    Apply writes the marker with `attempts = 0` and exits. The next start increments it and, if it
    does reach a healthy service, marks the apply done. A start that never gets there leaves
    `attempts = 1`, so the start after that restores the previous override file and records why.
    """
    root = Path(data_dir)
    overrides = _startup_values(read_json(root / OVERRIDE_FILE))
    state = read_json(root / APPLY_FILE)
    if state.get("status") != "pending":
        return overrides
    if int(state.get("attempts") or 0) >= 1:
        previous = _startup_values(state.get("previous"))
        write_json(root / OVERRIDE_FILE, previous)
        state.update(
            {
                "status": "failed",
                "reason": "新设置未能启动，已恢复上一份启动设置",
                "finished_at": _now(),
            }
        )
        write_json(root / APPLY_FILE, state)
        return previous
    state["attempts"] = 1
    write_json(root / APPLY_FILE, state)
    return overrides


_base = Settings()
# Where the startup files live: the configured data directory, not one an override may point at.
base_data_dir = _base.data_dir
settings = Settings(**recover_startup(base_data_dir))
