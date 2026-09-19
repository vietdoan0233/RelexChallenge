import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import cases, deps, evidence, ingestion, meta, privacy, radar
from app.core.config import get_settings
from app.privacy import ops, service

settings = get_settings()
_LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Resolve any unfinished privacy operation before serving a request
    (CLAUDE.md 18.10). Failure leaves the lock in place, so requests are
    refused rather than served from an inconsistent state."""
    current = get_settings()
    try:
        service.recover(
            source_dir=current.source_data_dir_resolved,
            db_path=current.database_path_resolved,
            ops_dir=current.privacy_ops_dir_resolved,
            artifact_dirs=current.derived_artifact_dirs_resolved,
        )
    except Exception as exc:
        _LOGGER.error("privacy recovery incomplete error_type=%s", type(exc).__name__)
    # Whatever recovery changed, never serve from a matrix loaded before it.
    deps.reset_shared_index()
    yield


app = FastAPI(
    title=settings.app_name_display,
    description="Evidence-first organizational memory auditor",
    lifespan=lifespan,
)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(ingestion.router)
app.include_router(privacy.router)
app.include_router(radar.router)
app.include_router(meta.router)


@app.exception_handler(ops.PrivacyLockedError)
async def _locked(_request: Request, _exc: ops.PrivacyLockedError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "A privacy operation is in progress; please try again shortly."},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database_path": get_settings().database_path}


# One-process mode: when the frontend has been built (`npm run build`), the API
# server also serves it, so the whole app runs from `uvicorn app.main:app`. It is
# mounted last so every /api route wins. The UI uses hash routing, so no
# server-side fallback is needed.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (_FRONTEND_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
