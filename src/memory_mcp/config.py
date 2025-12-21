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
    similarity_threshold: float = 0.85
    llm_model: str = Field(
        default="anthropic/claude-3-haiku",
        validation_alias=AliasChoices("MEMORY_MCP_LLM_MODEL", "LLM_MODEL"),
    )
    
    class Config:
        env_prefix = "MEMORY_MCP_"
        env_file = ".env"
        extra = "ignore" 

settings = Settings()
