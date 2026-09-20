"""Universal participant profile endpoints (CLAUDE.md 18.0.2, 20).

Every speaker/sender/mention/citation/timeline node is clickable to one of
these -- DB-hydrated only, for both ACTIVE and PSEUDONYMISED subjects. This
router never imports app/privacy/vault.py.
"""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api import deps
from app.privacy import profile

router = APIRouter(prefix="/api/people", tags=["people"])

Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]

_NO_STORE = {"Cache-Control": "private, no-store, max-age=0"}


@router.get("/{subject_id}")
def get_person(subject_id: str, conn: Conn, response: Response) -> dict:
    response.headers.update(_NO_STORE)
    detail = profile.get_profile(conn, subject_id)
    if detail is None:
        raise HTTPException(404, "Subject not found.")
    return {
        "subject_id": detail.subject_id,
        "display_alias": detail.display_alias,
        "privacy_state": detail.privacy_state,
        "display_name": detail.display_name,
        "author_units": detail.author_units,
        "speaker_units": detail.speaker_units,
        "mentioned_units": detail.mentioned_units,
        "pseudonymised_at": detail.pseudonymised_at,
        "verification_result": detail.verification_result,
    }


@router.get("/{subject_id}/history")
def get_person_history(subject_id: str, conn: Conn, response: Response) -> list[dict]:
    response.headers.update(_NO_STORE)
    detail = profile.get_profile(conn, subject_id)
    if detail is None:
        raise HTTPException(404, "Subject not found.")
    return [entry.__dict__ for entry in detail.history]
