import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api import deps
from app.schemas.receipt import EvidenceView
from app.validation import receipt_validator

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]

# Evidence text is application-owned personal/organizational data; never
# cached by a browser or intermediate proxy (matches app/api/privacy.py and
# app/api/people.py's header, and CLAUDE.md's privacy-hardening item).
_NO_STORE = {"Cache-Control": "private, no-store, max-age=0"}


@router.get("/{evidence_id}", response_model=EvidenceView)
def get_evidence(evidence_id: str, conn: Conn, response: Response) -> EvidenceView:
    response.headers.update(_NO_STORE)
    view = receipt_validator.evidence_view(conn, evidence_id)
    if view is None:
        raise HTTPException(404, "Evidence not found.")
    return view
