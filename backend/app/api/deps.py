"""Request-scoped dependencies.

One SQLite connection per request (connections are not shared across the
server's worker threads). The loaded embedding matrix is the one shared,
process-wide object; it must be reset after any deletion or rebuild so a
cached matrix can never resurrect removed evidence.
"""

import threading
from collections.abc import Iterator
from functools import lru_cache

from app.core.config import get_settings
from app.db import migrations
from app.db.connection import connect
from app.ingestion.embeddings import EmbeddingProvider, OpenAICompatibleEmbeddingProvider
from app.reasoning.llm import LLMClient, OpenAICompatibleChatClient
from app.retrieval.semantic import SemanticIndex, SemanticIndexError

_index_lock = threading.Lock()
_index: SemanticIndex | None = None
_index_loaded = False


def get_conn() -> Iterator:
    conn = connect(str(get_settings().database_path_resolved))
    try:
        migrations.initialize(conn)
        yield conn
    finally:
        conn.close()


def get_shared_index() -> SemanticIndex | None:
    global _index, _index_loaded
    with _index_lock:
        if not _index_loaded:
            conn = connect(str(get_settings().database_path_resolved))
            try:
                _index = SemanticIndex.load(conn)
            except SemanticIndexError:
                _index = None
            finally:
                conn.close()
            _index_loaded = True
        return _index


def reset_shared_index() -> None:
    """Call after a deletion/rebuild (Phase 5)."""
    global _index, _index_loaded
    with _index_lock:
        _index, _index_loaded = None, False


@lru_cache
def get_embedding_provider() -> EmbeddingProvider | None:
    settings = get_settings()
    if not settings.has_complete_embedding_configuration:
        return None
    return OpenAICompatibleEmbeddingProvider(
        api_key=settings.gpt_api_key,
        base_url=settings.gpt_base_url,
        model_name=settings.gpt_embedding_model,
    )


@lru_cache
def get_llm() -> LLMClient | None:
    settings = get_settings()
    if not (settings.gpt_api_key and settings.gpt_base_url and settings.gpt_model):
        return None
    return OpenAICompatibleChatClient(
        api_key=settings.gpt_api_key,
        base_url=settings.gpt_base_url,
        model_name=settings.gpt_model,
    )
