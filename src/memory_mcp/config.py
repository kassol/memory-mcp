import os
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


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


settings = Settings()
