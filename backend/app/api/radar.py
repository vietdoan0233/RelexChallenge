import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.core.config import get_settings
from app.radar import service
from app.radar.schemas import FindingCard

router = APIRouter(prefix="/api/radar", tags=["radar"])

Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]


@router.get("", response_model=list[FindingCard])
def list_findings(conn: Conn) -> list[FindingCard]:
    """Precomputed findings only: nothing is generated on request, so the page
    always opens with candidates already surfaced."""
    return service.load_findings(conn, get_settings().source_data_dir_resolved)


@router.get("/{finding_id}", response_model=FindingCard)
def get_finding(finding_id: str, conn: Conn) -> FindingCard:
    for card in service.load_findings(conn, get_settings().source_data_dir_resolved):
        if card.finding_id == finding_id:
            return card
    raise HTTPException(404, "Finding not found.")
