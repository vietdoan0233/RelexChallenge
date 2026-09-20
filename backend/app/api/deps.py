"""Request-scoped dependencies.

One SQLite connection per request (connections are not shared across the
server's worker threads). The loaded embedding matrix is the one shared,
process-wide object; it must be reset after any deletion or rebuild so a
cached matrix can never resurrect removed evidence.
"""

import threading
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Header, HTTPException

from app.core.config import get_settings
from app.db import migrations
from app.db.connection import connect
from app.ingestion.embeddings import EmbeddingProvider, OpenAICompatibleEmbeddingProvider
from app.privacy import ops
from app.privacy.gate import gate
from app.reasoning.llm import LLMClient, OpenAICompatibleChatClient
from app.retrieval.semantic import SemanticIndex, SemanticIndexError

_index_lock = threading.Lock()
_index: SemanticIndex | None = None
_index_loaded = False


def get_conn() -> Iterator:
    # While a privacy operation is active, source and database may disagree;
    # nothing may read them (CLAUDE.md 18.10). The file-based lock catches a
    # *new* request; the in-process read lease additionally blocks a request
    # already mid-flight from continuing once a write starts, and is held
    # for the connection's entire lifetime, not just at connect time.
    ops.assert_unlocked(get_settings().privacy_ops_dir_resolved)
    with gate.read_lease():
        conn = connect(str(get_settings().database_path_resolved))
        try:
            migrations.initialize(conn)
            yield conn
        finally:
            conn.close()


def get_conn_for_privacy_write() -> Iterator:
    """For the pseudonymisation and admin-reversal endpoints only: these
    handlers call into app/privacy/pseudonymise.py or app/privacy/reverse.py,
    which acquire gate.write_lease() themselves and wait for every
    outstanding *read* lease to drain first. Handing such a handler a
    connection wrapped in gate.read_lease() (as get_conn does for every
    other endpoint) would make the request wait for its own read lease to
    drain before its write lease could ever be granted -- a permanent
    self-deadlock, not a race. These two endpoints' own write operation is
    what provides exclusivity here; they do not also need a read lease."""
    ops.assert_unlocked(get_settings().privacy_ops_dir_resolved)
    conn = connect(str(get_settings().database_path_resolved))
    try:
        # Schema initialization can rebuild FTS, so it is an archive write.
        # Serialize that short setup phase before the handler acquires its
        # own write lease for the actual privacy operation.
        with gate.write_lease():
            ops.assert_unlocked(get_settings().privacy_ops_dir_resolved)
            migrations.initialize(conn)
        yield conn
    finally:
        conn.close()


def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    """Gates pseudonymisation and the admin reversal endpoint. Fails closed:
    an unset PRIVACY_ADMIN_TOKEN means every request is unauthorized, never
    "no auth required" -- and `confirm=true` in a request body is never
    treated as authorization on its own."""
    settings = get_settings()
    if not settings.privacy_admin_token:
        raise HTTPException(401, "Admin operations are not configured.")
    if authorization != f"Bearer {settings.privacy_admin_token}":
        raise HTTPException(401, "Invalid or missing admin credentials.")


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
