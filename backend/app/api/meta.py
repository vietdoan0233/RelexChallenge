import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api import deps

router = APIRouter(prefix="/api", tags=["meta"])

Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]


@router.get("/stats")
def stats(conn: Conn) -> dict:
    """Archive facts for the home page. Counts only: no evidence text and no
    person names, so it is safe to show before anyone has asked anything."""

    def count(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0])

    span = conn.execute("SELECT MIN(event_date), MAX(event_date) FROM evidence_units").fetchone()
    by_type = {
        row[0]: row[1]
        for row in conn.execute("SELECT document_type, COUNT(*) FROM documents GROUP BY 1")
    }
    return {
        "documents": count("SELECT COUNT(*) FROM documents"),
        "documents_by_type": by_type,
        "evidence_units": count("SELECT COUNT(*) FROM evidence_units"),
        "people": count("SELECT COUNT(*) FROM people"),
        "embeddings": count("SELECT COUNT(*) FROM evidence_embeddings"),
        "cases": count("SELECT COUNT(*) FROM cases WHERE query NOT LIKE 'Reconsideration:%'"),
        "radar_findings": count(
            "SELECT COUNT(*) FROM pulse_findings WHERE category = 'RECONSIDERATION_CANDIDATE'"
        ),
        "first_date": span[0],
        "last_date": span[1],
    }
