import json
import os
from pathlib import Path


def _config_path() -> Path:
    return Path(os.environ.get("MEM_CONFIG_PATH", Path.home() / ".config" / "memory-mcp" / "config.json"))


def load_config() -> dict:
    """Load config from file, env vars override file values."""
    cfg = {"api_url": "http://localhost:8765", "api_key": ""}
    path = _config_path()
    if path.exists():
        with open(path) as f:
            cfg.update(json.load(f))
    cfg["api_url"] = os.environ.get("MEMORY_MCP_API_URL", cfg["api_url"])
    cfg["api_key"] = os.environ.get("MEMORY_MCP_API_KEY", cfg["api_key"])
    return cfg
