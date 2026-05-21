import logging
import threading
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False
_jieba_module = None


def _get_jieba():
    global _initialized, _jieba_module
    if _jieba_module is not None:
        return _jieba_module
    with _lock:
        if _jieba_module is not None:
            return _jieba_module
        import jieba  # lazy import — avoid loading dictionary at process startup
        jieba.setLogLevel(logging.WARNING)
        if settings.jieba_user_dict_path:
            try:
                jieba.load_userdict(settings.jieba_user_dict_path)
                logger.info("Loaded jieba user dict from %s", settings.jieba_user_dict_path)
            except Exception as exc:
                logger.warning("Failed to load jieba user dict: %s", exc)
        _jieba_module = jieba
        _initialized = True
        return _jieba_module


def tokenize(text: Optional[str]) -> str:
    """Tokenize text with jieba (precise mode) and return space-joined tokens.

    Used to populate `memories.content_tokens` / `title_tokens` columns.
    FTS5 indexes those columns with `unicode61`, so the application layer owns
    Chinese segmentation and the database layer stays C-compile-free.
    """
    if not text:
        return ""
    stripped = text.strip()
    if not stripped:
        return ""
    jieba = _get_jieba()
    tokens = [t for t in jieba.cut(stripped, cut_all=False) if t and not t.isspace()]
    return " ".join(tokens)


def reset_for_tests() -> None:
    """Force re-initialization (used by tests after env change)."""
    global _initialized, _jieba_module
    with _lock:
        _initialized = False
        _jieba_module = None
