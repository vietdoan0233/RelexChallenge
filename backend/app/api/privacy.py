import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api import deps
from app.core.config import get_settings
from app.ingestion.embeddings import EmbeddingProvider
from app.privacy import service, targets
from app.privacy.ops import PrivacyOperationError

router = APIRouter(prefix="/api/privacy", tags=["privacy"])

Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]
Embedder = Annotated[EmbeddingProvider | None, Depends(deps.get_embedding_provider)]


class PersonBody(BaseModel):
    person_id: str = Field(min_length=1, max_length=200)


class PurgeBody(PersonBody):
    # A destructive, irreversible action must be an explicit, deliberate request.
    confirm: bool = False


@router.get("/people")
def list_people(conn: Conn) -> list[dict]:
    return [
        {
            "person_id": p.person_id,
            "canonical_name": p.canonical_name,
            "author_units": p.author_units,
            "speaker_units": p.speaker_units,
            "mentioned_units": p.mentioned_units,
        }
        for p in targets.list_people(conn)
    ]


@router.post("/preview")
def preview(body: PersonBody, conn: Conn) -> dict:
    result = service.preview(conn, get_settings().source_data_dir_resolved, body.person_id)
    if result is None:
        raise HTTPException(404, "Person not found.")
    return result.__dict__


@router.post("/purge")
def purge(body: PurgeBody, conn: Conn, embedder: Embedder) -> dict:
    """Irreversible. Returns counts and verification state only -- never the
    removed person's content or identifiers."""
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true to run an irreversible operation.")
    settings = get_settings()
    try:
        result = service.purge(
            conn,
            source_dir=settings.source_data_dir_resolved,
            db_path=settings.database_path_resolved,
            ops_dir=settings.privacy_ops_dir_resolved,
            person_id=body.person_id,
            artifact_dirs=settings.derived_artifact_dirs_resolved,
            provider=embedder,
        )
    except PrivacyOperationError:
        raise HTTPException(
            500, "The privacy operation did not complete; the system is locked for review."
        ) from None
    # A cached matrix must never resurrect removed evidence.
    deps.reset_shared_index()
    return result.__dict__
