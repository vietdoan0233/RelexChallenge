import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.schemas.receipt import EvidenceView
from app.validation import receipt_validator

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]


@router.get("/{evidence_id}", response_model=EvidenceView)
def get_evidence(evidence_id: str, conn: Conn) -> EvidenceView:
    view = receipt_validator.evidence_view(conn, evidence_id)
    if view is None:
        raise HTTPException(404, "Evidence not found.")
    return view
