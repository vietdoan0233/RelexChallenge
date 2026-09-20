"""Admin-only reversal endpoint (CLAUDE.md 18.0.7).

Deliberately outside /api/privacy: reversal is not a standard profile/
search/evidence capability and is never available merely because a caller
knows a subject_id or display_alias. Gated by the same admin-token
dependency as pseudonymisation.
"""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.api import deps
from app.core.config import get_settings
from app.ingestion.embeddings import EmbeddingProvider
from app.privacy import reverse
from app.privacy.ops import PrivacyOperationError

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(deps.require_admin)])

# Not get_conn: reverse_pseudonymisation acquires the write lease itself
# and must not also be holding a read lease on its own connection while
# doing so (see deps.get_conn_for_privacy_write's docstring).
Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn_for_privacy_write)]
Embedder = Annotated[EmbeddingProvider | None, Depends(deps.get_embedding_provider)]

_NO_STORE = {"Cache-Control": "private, no-store, max-age=0"}


class ReversalBody(BaseModel):
    # A hard-to-reverse admin action must be an explicit, deliberate
    # request, mirroring the old v1.5 purge endpoint's confirm=true
    # requirement -- the admin bearer token alone authenticates the
    # *caller*, it does not confirm *this specific* destructive intent.
    confirm: bool = False


@router.post("/people/{subject_id}/reverse-pseudonymisation")
def reverse_pseudonymisation(
    subject_id: str, body: ReversalBody, conn: Conn, embedder: Embedder, response: Response
) -> dict:
    """Response contains status, subject ID, operation ID, and verification
    result -- never the vault bundle."""
    response.headers.update(_NO_STORE)
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true to reverse this subject's pseudonymisation.")
    settings = get_settings()
    try:
        result = reverse.reverse_pseudonymisation(
            conn,
            source_dir=settings.source_data_dir_resolved,
            db_path=settings.database_path_resolved,
            ops_dir=settings.privacy_ops_dir_resolved,
            vault_path=settings.pseudonym_vault_path_resolved,
            vault_key=settings.pseudonym_vault_key,
            subject_id=subject_id,
            confirm=body.confirm,
            artifact_dirs=settings.derived_artifact_dirs_resolved,
            provider=embedder,
        )
    except PrivacyOperationError:
        raise HTTPException(
            500, "The reversal operation did not complete; the system is locked for review."
        ) from None
    deps.reset_shared_index()
    response.headers["Clear-Site-Data"] = '"cache"'
    return result.__dict__
