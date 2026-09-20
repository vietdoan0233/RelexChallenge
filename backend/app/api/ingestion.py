import sqlite3
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from app.api import deps
from app.core.config import get_settings
from app.ingestion import upload
from app.ingestion.embeddings import EmbeddingProvider

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])

Embedder = Annotated[EmbeddingProvider | None, Depends(deps.get_embedding_provider)]
Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]


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


_TYPE_DIRS = {"EMAIL": "emails", "TRANSCRIPT": "transcripts", "REPORT": "reports"}


@router.get("/recent")
def recent_documents(
    conn: Conn, paths: Paths, limit: Annotated[int, Query(ge=1, le=50)] = 5
) -> list[dict]:
    """The most recently added documents, newest first. "Added" is the canonical
    source file's modification time, so it reflects when the file entered the
    archive rather than anything a client claims. Counts only -- no evidence text."""
    rows = conn.execute(
        "SELECT d.document_id, d.filename, d.document_type, d.title, "
        "COUNT(u.evidence_id) AS units, COUNT(e.evidence_id) AS embedded "
        "FROM documents d "
        "LEFT JOIN evidence_units u ON u.document_id = d.document_id "
        "LEFT JOIN evidence_embeddings e ON e.evidence_id = u.evidence_id "
        "GROUP BY d.document_id"
    ).fetchall()
    found = []
    for row in rows:
        subdir = _TYPE_DIRS.get(row["document_type"])
        path = paths.source_dir / subdir / row["filename"] if subdir else None
        if path is None or not path.is_file():
            continue
        found.append((path.stat().st_mtime, row))
    found.sort(key=lambda item: (-item[0], item[1]["filename"]))
    return [
        {
            "document_id": row["document_id"],
            "filename": row["filename"],
            "document_type": row["document_type"],
            "title": row["title"],
            "evidence_units": row["units"],
            "indexed": "full" if row["embedded"] >= row["units"] else "keyword",
            "added_at": datetime.fromtimestamp(mtime, UTC).isoformat(),
        }
        for mtime, row in found[:limit]
    ]
