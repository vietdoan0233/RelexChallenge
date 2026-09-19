import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api import deps
from app.core.errors import AnalysisUnavailableError
from app.ingestion.embeddings import EmbeddingProvider
from app.reasoning.llm import LLMClient
from app.reasoning.service import CaseService, load_case_receipt
from app.retrieval.semantic import SemanticIndex
from app.retrieval.service import RetrievalService
from app.schemas.receipt import CaseReceipt

router = APIRouter(prefix="/api/cases", tags=["cases"])
_LOGGER = logging.getLogger(__name__)

Conn = Annotated[sqlite3.Connection, Depends(deps.get_conn)]
Llm = Annotated[LLMClient | None, Depends(deps.get_llm)]
Embedder = Annotated[EmbeddingProvider | None, Depends(deps.get_embedding_provider)]
Index = Annotated[SemanticIndex | None, Depends(deps.get_shared_index)]


class QueryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)


@router.post("/query", response_model=CaseReceipt)
def query_case(
    body: QueryRequest, conn: Conn, llm: Llm, embedder: Embedder, index: Index
) -> CaseReceipt:
    if llm is None:
        raise HTTPException(503, "The reasoning service is not configured.")
    retrieval = RetrievalService(conn, embedder, index=index)
    try:
        receipt, _trace = CaseService(conn, retrieval, llm).answer(body.query.strip())
    except AnalysisUnavailableError:
        # Explicit failure, never a fabricated answer (CLAUDE.md 22).
        raise HTTPException(503, "Analysis is temporarily unavailable. Please try again.") from None
    return receipt


@router.get("/{case_id}", response_model=CaseReceipt)
def get_case(case_id: str, conn: Conn) -> CaseReceipt:
    receipt = load_case_receipt(conn, case_id)
    if receipt is None:
        raise HTTPException(404, "Case not found.")
    return receipt
