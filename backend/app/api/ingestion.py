from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.api import deps
from app.core.config import get_settings
from app.ingestion import upload
from app.ingestion.embeddings import EmbeddingProvider

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])

Embedder = Annotated[EmbeddingProvider | None, Depends(deps.get_embedding_provider)]


def get_paths() -> upload.IngestPaths:
    """Overridable in tests so destructive work stays inside a temp directory."""
    settings = get_settings()
    return upload.IngestPaths(
        source_dir=settings.source_data_dir_resolved,
        db_path=settings.database_path_resolved,
        ops_dir=settings.privacy_ops_dir_resolved,
        staging_root=settings.database_path_resolved.parent / "cache" / "uploads",
    )


Paths = Annotated[upload.IngestPaths, Depends(get_paths)]


def _read_bounded(file: UploadFile) -> bytes:
    # One byte over the limit is enough to know the file is too large without
    # reading the rest of a hostile upload into memory.
    return file.file.read(upload.MAX_FILE_BYTES + 1)


@router.post("/upload")
def upload_evidence(
    document_type: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    paths: Paths,
    embedder: Embedder,
) -> JSONResponse:
    """Add .txt emails, meeting transcripts or reports to the canonical archive.

    Returns 200 only after the files are in ``data/source/`` and the database
    has been rebuilt from it. Any other outcome is a 4xx/5xx and leaves no new
    files behind."""
    try:
        payload = [(f.filename, _read_bounded(f)) for f in files]
        result = upload.add_evidence(payload, document_type.strip().lower(), paths, embedder)
    except upload.UploadRejected as rejected:
        return JSONResponse(
            status_code=rejected.status_code,
            content={
                "status": "failed",
                "detail": rejected.message,
                "failures": rejected.failures,
                "files_removed": rejected.files_removed,
            },
        )
    finally:
        # The semantic index is a process-wide cache of the embedding table;
        # after any run that may have rebuilt it, a stale matrix would hide
        # the new evidence from retrieval.
        deps.reset_shared_index()
    return JSONResponse(content=result.__dict__ | {"files": [f.__dict__ for f in result.files]})
