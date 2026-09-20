import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, cases, deps, evidence, ingestion, meta, people, privacy, radar
from app.core.config import get_settings
from app.db import migrations, repository
from app.db.connection import connect
from app.privacy import ops, pseudonymise
from app.privacy.gate import gate
from app.radar import startup as radar_startup

settings = get_settings()
_LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Resolve any unfinished privacy operation before serving a request
    (CLAUDE.md 18.10). Failure leaves the lock in place, so requests are
    refused rather than served from an inconsistent state."""
    current = get_settings()
    try:
        pseudonymise.recover(
            source_dir=current.source_data_dir_resolved,
            db_path=current.database_path_resolved,
            ops_dir=current.privacy_ops_dir_resolved,
            vault_path=current.pseudonym_vault_path_resolved,
            vault_key=current.pseudonym_vault_key,
            artifact_dirs=current.derived_artifact_dirs_resolved,
        )
    except Exception as exc:
        _LOGGER.error("privacy recovery incomplete error_type=%s", type(exc).__name__)
    # Whatever recovery changed, never serve from a matrix loaded before it.
    deps.reset_shared_index()
    radar_task = None
    if current.radar_startup_refresh:
        radar_task = asyncio.create_task(
            asyncio.to_thread(radar_startup.refresh_if_needed, current),
            name="radar-startup-refresh",
        )
    try:
        yield
    finally:
        # The worker owns its database connection. Cancel the awaitable during
        # shutdown so a slow provider does not hold the ASGI lifecycle open;
        # the process will dispose of the worker when it exits.
        if radar_task is not None and not radar_task.done():
            radar_task.cancel()
        if radar_task is not None:
            try:
                await radar_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title=settings.app_name_display,
    description="Evidence-first organizational memory auditor",
    lifespan=lifespan,
)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(ingestion.router)
app.include_router(privacy.router)
app.include_router(people.router)
app.include_router(admin.router)
app.include_router(radar.router)
app.include_router(meta.router)


@app.exception_handler(ops.PrivacyLockedError)
async def _locked(_request: Request, _exc: ops.PrivacyLockedError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "A privacy operation is in progress; please try again shortly."},
    )


@app.exception_handler(ops.ArchiveWriteBusyError)
async def _archive_write_busy(_request: Request, _exc: ops.ArchiveWriteBusyError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "Another archive write is running; please try again shortly."},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    # Never the filesystem path (CLAUDE.md hardening item): "configured" is
    # enough for a liveness check, and a path leak is otherwise pure noise
    # to anyone but an operator with the .env in hand anyway.
    return {"status": "ok"}


def _validate_embedding_vectors(conn) -> tuple[int, int]:
    """(valid_count, invalid_count) over every stored embedding row. A row
    counts as valid only if vector_json parses as JSON, is a non-empty list
    of finite numbers, and has the same dimension as every other valid row
    seen so far -- re-validating what app/ingestion/embeddings.py already
    checks at write time, as an independent readiness-time guarantee (a row
    could predate that validation, or the file could have been touched
    outside the app)."""
    valid = invalid = 0
    dimensions: int | None = None
    for row in conn.execute("SELECT vector_json FROM evidence_embeddings"):
        ok = False
        try:
            vector = json.loads(row["vector_json"])
            if isinstance(vector, list) and vector:
                arr = np.asarray(vector, dtype=float)
                if arr.ndim == 1 and bool(np.isfinite(arr).all()):
                    if dimensions is None:
                        dimensions = int(arr.size)
                    ok = arr.size == dimensions
        except (TypeError, ValueError):
            ok = False
        valid, invalid = (valid + 1, invalid) if ok else (valid, invalid + 1)
    return valid, invalid


@app.get("/api/readiness")
def readiness() -> JSONResponse:
    """Distinct from /api/health: readiness additionally fails if the
    runtime database is empty, stale relative to the current source
    snapshot, missing or invalid embeddings, short of the expected
    clean-archive baseline, or if a privacy operation is locked/incomplete
    -- the checks a judge rehearsal or a deploy step should gate on before
    trusting the archive.

    Deliberately does not go through app.api.deps.get_conn (which itself
    refuses to run while locked): that is correct for every *other*
    endpoint, but would turn "locked" into an opaque 503 here instead of
    one legible check among several. Still protected by the same privacy
    gate as every normal reader, just applied explicitly: the file-based
    lock is checked first (and every DB-dependent check short-circuits to
    False, without opening a connection, if it is held), and the brief
    in-process read is additionally taken under gate.read_lease() so a
    write that starts between those two checks cannot be read mid-mutation
    either. This never mutates anything.
    """
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}

    current = get_settings()
    locked = ops.is_locked(current.privacy_ops_dir_resolved)
    checks["privacy_operation_not_locked"] = not locked
    checks["vault_configured"] = bool(current.pseudonym_vault_key)

    db_dependent_checks = (
        "database_not_empty",
        "fts_matches_evidence_units",
        "embeddings_cover_all_evidence",
        "embeddings_are_valid",
        "runtime_database_not_stale",
        "matches_expected_clean_archive_baseline",
    )
    db_path = current.database_path_resolved

    def _mark_unavailable() -> None:
        for key in db_dependent_checks:
            checks[key] = False

    if locked or not db_path.exists():
        # While locked, source and database may temporarily disagree
        # (18.10); reading either risks reporting a torn mid-mutation state.
        _mark_unavailable()
    else:
        try:
            with gate.read_lease():
                conn = connect(str(db_path))
                try:
                    migrations.initialize(conn)
                    document_count = len(repository.all_documents(conn))
                    evidence_units = repository.all_evidence_units(conn)
                    fts_rows = repository.fts_row_count(conn)
                    embedding_rows = repository.embedding_row_count(conn)
                    valid_embeddings, invalid_embeddings = _validate_embedding_vectors(conn)

                    checks["database_not_empty"] = document_count > 0 and len(evidence_units) > 0
                    checks["fts_matches_evidence_units"] = fts_rows == len(evidence_units)
                    # Embeddings are "ready" only when every evidence unit has
                    # one; a partially-embedded archive is reported, not
                    # silently treated as ready (CLAUDE.md 8.1).
                    checks["embeddings_cover_all_evidence"] = len(
                        evidence_units
                    ) > 0 and embedding_rows == len(evidence_units)
                    checks["embeddings_are_valid"] = (
                        invalid_embeddings == 0 and valid_embeddings == embedding_rows
                    )

                    source_dir = current.source_data_dir_resolved
                    source_newer = False
                    if source_dir.exists():
                        newest_source = max(
                            (p.stat().st_mtime for p in source_dir.rglob("*") if p.is_file()),
                            default=0,
                        )
                        source_newer = newest_source > db_path.stat().st_mtime
                    checks["runtime_database_not_stale"] = not source_newer

                    checks["matches_expected_clean_archive_baseline"] = (
                        document_count == current.expected_document_count
                        and len(evidence_units) == current.expected_evidence_unit_count
                        and fts_rows == current.expected_fts_row_count
                        and valid_embeddings == current.expected_embedding_row_count
                    )

                    details["documents"] = document_count
                    details["evidence_units"] = len(evidence_units)
                    details["fts_rows"] = fts_rows
                    details["embedding_rows"] = embedding_rows
                    details["valid_embeddings"] = valid_embeddings
                    details["invalid_embeddings"] = invalid_embeddings
                finally:
                    conn.close()
        except ops.PrivacyLockedError:
            # A write started between the is_locked() check above and here.
            checks["privacy_operation_not_locked"] = False
            _mark_unavailable()

    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"ready": ready, "checks": checks, "details": details},
    )


# One-process mode: when the frontend has been built (`npm run build`), the API
# server also serves it, so the whole app runs from `uvicorn app.main:app`. It is
# mounted last so every /api route wins. The UI uses hash routing, so no
# server-side fallback is needed.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (_FRONTEND_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
