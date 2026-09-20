import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api import deps
from app.core.config import get_settings
from app.ingestion.embeddings import EmbeddingProvider
from app.privacy import pseudonymise, targets
from app.privacy.ops import PrivacyOperationError

router = APIRouter(prefix="/api/privacy", tags=["privacy"])

Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]
# Not get_conn: run_pseudonymise acquires the write lease itself and must
# not also be holding a read lease on its own connection while doing so
# (see deps.get_conn_for_privacy_write's docstring).
WriteConn = Annotated[sqlite3.Connection, Depends(deps.get_conn_for_privacy_write)]
Embedder = Annotated[EmbeddingProvider | None, Depends(deps.get_embedding_provider)]

# Personal data must never be cached by a browser/proxy (privacy hardening
# item in the v1.6 brief).
_NO_STORE = {"Cache-Control": "private, no-store, max-age=0"}


class SubjectBody(BaseModel):
    subject_id: str = Field(min_length=1, max_length=200)


@router.get("/people")
def list_people(conn: Conn, response: Response) -> list[dict]:
    response.headers.update(_NO_STORE)
    return [
        {
            "subject_id": p.subject_id,
            "display_alias": p.display_alias,
            "privacy_state": p.privacy_state,
            "display_name": p.display_name,
            "author_units": p.author_units,
            "speaker_units": p.speaker_units,
            "mentioned_units": p.mentioned_units,
        }
        for p in targets.list_people(conn)
    ]


@router.post("/preview")
def preview(body: SubjectBody, conn: Conn, response: Response) -> dict:
    response.headers.update(_NO_STORE)
    result = pseudonymise.preview(conn, get_settings().source_data_dir_resolved, body.subject_id)
    if result is None:
        raise HTTPException(404, "Subject not found, or already pseudonymised.")
    return result.__dict__


@router.post("/pseudonymise", dependencies=[Depends(deps.require_admin)])
def run_pseudonymise(
    body: SubjectBody, conn: WriteConn, embedder: Embedder, response: Response
) -> dict:
    """Admin-only. Returns counts, subject_id, display_alias, state,
    operation ID, and verification result -- never the original identity."""
    response.headers.update(_NO_STORE)
    settings = get_settings()
    try:
        result = pseudonymise.pseudonymise(
            conn,
            source_dir=settings.source_data_dir_resolved,
            db_path=settings.database_path_resolved,
            ops_dir=settings.privacy_ops_dir_resolved,
            vault_path=settings.pseudonym_vault_path_resolved,
            vault_key=settings.pseudonym_vault_key,
            subject_id=body.subject_id,
            artifact_dirs=settings.derived_artifact_dirs_resolved,
            provider=embedder,
        )
    except PrivacyOperationError:
        raise HTTPException(
            500, "The pseudonymisation operation did not complete; the system is locked for review."
        ) from None
    # A cached matrix must never keep serving pre-pseudonymisation text.
    deps.reset_shared_index()
    response.headers["Clear-Site-Data"] = '"cache"'
    return result.__dict__
