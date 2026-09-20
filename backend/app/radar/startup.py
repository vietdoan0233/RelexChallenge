"""Best-effort Radar initialization for an application session.

Radar findings are derived data. A server session should make a missing set
of findings self-healing, but a provider outage must not prevent the rest of
the application from starting or erase a previously usable set.
"""

import logging
from pathlib import Path

from app.core.config import Settings
from app.db import migrations
from app.db.connection import connect
from app.ingestion.embeddings import OpenAICompatibleEmbeddingProvider
from app.privacy import ops
from app.privacy.gate import gate
from app.radar import service
from app.reasoning.llm import OpenAICompatibleChatClient
from app.retrieval.service import RetrievalService

_LOGGER = logging.getLogger(__name__)


def refresh_if_needed(settings: Settings) -> None:
    """Generate Radar findings while the current instance is below target.

    This function is intended to run in a background thread from the FastAPI
    lifespan. It owns its SQLite connection and uses the same privacy gate as
    other application writers. Logs contain counts and exception types only;
    evidence text and provider responses never enter logs.
    """
    if not settings.radar_startup_refresh:
        _LOGGER.info("radar startup refresh disabled")
        return

    db_path = settings.database_path_resolved
    source_dir = settings.source_data_dir_resolved
    if not db_path.exists():
        _LOGGER.info("radar startup refresh skipped: runtime database is missing")
        return
    if not source_dir.is_dir():
        _LOGGER.info("radar startup refresh skipped: source directory is missing")
        return
    if not (settings.gpt_api_key and settings.gpt_base_url and settings.gpt_model):
        _LOGGER.info("radar startup refresh skipped: reasoning service is not configured")
        return
    if ops.is_locked(settings.privacy_ops_dir_resolved):
        _LOGGER.info("radar startup refresh skipped: privacy operation is locked")
        return

    try:
        # Radar performs slow provider calls. Keep it compatible with normal
        # readers while preventing privacy/ingestion writers from overlapping
        # the evidence snapshot and derived-record writes.
        with gate.read_lease():
            ops.assert_unlocked(settings.privacy_ops_dir_resolved)
            _refresh_locked(settings, db_path, source_dir)
    except Exception as exc:
        # Startup must remain available even when the provider or a derived
        # database operation is unavailable. The next session can retry.
        _LOGGER.warning("radar startup refresh failed error_type=%s", type(exc).__name__)


def _refresh_locked(settings: Settings, db_path: Path, source_dir: Path) -> None:
    conn = connect(str(db_path))
    try:
        migrations.initialize(conn)
        findings = service.load_findings(conn, source_dir)
        if len(findings) >= settings.radar_startup_target:
            _LOGGER.info(
                "radar startup refresh skipped: target reached findings=%s target=%s",
                len(findings),
                settings.radar_startup_target,
            )
            return

        llm = OpenAICompatibleChatClient(
            api_key=settings.gpt_api_key,
            base_url=settings.gpt_base_url,
            model_name=settings.gpt_model,
        )
        embedder = None
        if settings.has_complete_embedding_configuration:
            embedder = OpenAICompatibleEmbeddingProvider(
                api_key=settings.gpt_api_key,
                base_url=settings.gpt_base_url,
                model_name=settings.gpt_embedding_model,
            )
        result = service.run_radar(
            conn,
            RetrievalService(conn, embedder),
            llm,
            source_dir,
            limit=min(settings.radar_startup_maximum, service.MAX_FINDINGS),
        )
        _LOGGER.info(
            "radar startup refresh finished surfaced=%s rejected=%s dropped_unsupported=%s",
            len(result.surfaced),
            len(result.rejected),
            result.dropped_unsupported,
        )
    finally:
        conn.close()
