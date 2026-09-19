"""Semantic retrieval: stored embeddings + NumPy cosine similarity
(CLAUDE.md 9.2). No vector database: the corpus fits in memory."""

import json
import sqlite3
from dataclasses import dataclass

import numpy as np

from app.retrieval.lexical import DEFAULT_LIMIT, Hit


class SemanticIndexError(RuntimeError):
    """The stored embeddings cannot be used as a single coherent vector space."""


@dataclass
class SemanticIndex:
    model_name: str
    evidence_ids: list[str]
    event_dates: list[str | None]
    matrix: np.ndarray  # (n, d), rows L2-normalised

    @property
    def size(self) -> int:
        return len(self.evidence_ids)

    @property
    def dimensions(self) -> int:
        return int(self.matrix.shape[1]) if self.size else 0

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> "SemanticIndex | None":
        """Load every embedding whose unit still exists, or None if there are none.

        Refuses to mix models or dimensions: cosine similarity across two
        embedding spaces is meaningless, and a silent mix would look like a
        plausible-but-wrong ranking.
        """
        rows = conn.execute(
            "SELECT m.evidence_id, m.model_name, m.vector_json, e.event_date "
            "FROM evidence_embeddings AS m JOIN evidence_units AS e "
            "ON e.evidence_id = m.evidence_id ORDER BY m.evidence_id"
        ).fetchall()
        if not rows:
            return None

        models = {row["model_name"] for row in rows}
        if len(models) != 1:
            raise SemanticIndexError("stored embeddings come from more than one model")

        try:
            vectors = np.asarray([json.loads(row["vector_json"]) for row in rows], dtype=np.float32)
        except (ValueError, TypeError) as exc:
            # Malformed JSON, ragged rows, or non-numeric values all mean the
            # stored vectors are not one coherent space. Reported as a
            # SemanticIndexError so callers degrade to lexical-only.
            raise SemanticIndexError("stored embeddings are malformed or ragged") from exc
        if vectors.ndim != 2 or vectors.shape[1] == 0:
            raise SemanticIndexError("stored embeddings do not share one dimension")
        if not np.isfinite(vectors).all():
            raise SemanticIndexError("stored embeddings contain a non-finite value")

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return cls(
            model_name=models.pop(),
            evidence_ids=[row["evidence_id"] for row in rows],
            event_dates=[row["event_date"] for row in rows],
            matrix=vectors / norms,
        )

    def search(
        self,
        query_vector: list[float],
        *,
        limit: int = DEFAULT_LIMIT,
        after_date: str | None = None,
    ) -> list[Hit]:
        query = np.asarray(query_vector, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != self.dimensions:
            raise SemanticIndexError("query vector dimension does not match the stored embeddings")
        norm = float(np.linalg.norm(query))
        if norm == 0.0 or not np.isfinite(norm):
            raise SemanticIndexError("query vector is empty or non-finite")

        scores = self.matrix @ (query / norm)
        if after_date is not None:
            keep = np.array([d is not None and d > after_date for d in self.event_dates])
            scores = np.where(keep, scores, -np.inf)

        # Stable order (score desc, then evidence_id asc) keeps ties deterministic.
        order = sorted(
            (i for i in range(self.size) if np.isfinite(scores[i])),
            key=lambda i: (-float(scores[i]), self.evidence_ids[i]),
        )[:limit]
        return [
            Hit(evidence_id=self.evidence_ids[i], rank=position, score=float(scores[i]))
            for position, i in enumerate(order, start=1)
        ]
