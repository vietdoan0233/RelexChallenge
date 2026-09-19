"""Embedding generation.

Must never make the rest of ingestion depend on network access:
--skip-embeddings and a deterministic mock provider let schema, parsing,
FTS, and people/alias work fully offline (CLAUDE.md 8.1). A provider
failure is reported, not raised, so deterministic ingestion output still
succeeds when embeddings do not.

The organizer GPT transport is intentionally absent until its endpoint,
authentication, and request/response contract are supplied. The protocol
below is the stable boundary for that adapter.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Protocol

import numpy as np


class EmbeddingProvider(Protocol):
    model_name: str

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbeddingProvider:
    """Offline, dependency-free embedding stand-in for unit tests: a
    hash-seeded pseudo-random unit vector, stable for a given text across
    processes (sha256, not the builtin hash(), which Python salts per
    process) so cosine-similarity tests are reproducible without network
    access or an API key."""

    model_name = "mock-embedding-v1"
    dimensions = 16

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            seed = int.from_bytes(digest[:8], "big")
            rng = np.random.default_rng(seed)
            vector = rng.normal(size=self.dimensions)
            vectors.append((vector / np.linalg.norm(vector)).tolist())
        return vectors


@dataclass
class EmbeddingRunReport:
    attempted: int = 0
    succeeded: int = 0
    persisted_rows: int = 0
    skipped: bool = False
    error: str | None = None


_DEFAULT_BATCH_SIZE = 64
_DEFAULT_MAX_RETRIES = 2
_INITIAL_RETRY_DELAY_SECONDS = 0.25


def generate_embeddings(
    conn,
    evidence_rows: list[tuple[str, str]],
    provider: EmbeddingProvider | None,
    *,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    initial_retry_delay_seconds: float = _INITIAL_RETRY_DELAY_SECONDS,
) -> EmbeddingRunReport:
    """Generate embedding rows in bounded batches.

    ``provider=None`` means ``--skip-embeddings``. Transient provider failures
    are retried with bounded exponential backoff. A failed batch is never
    partly written: its vector count, numeric values, finiteness, and dimensions
    are validated before its rows are stored.
    Earlier successful batches remain usable and the caller receives a clear
    partial-failure report rather than a silently incomplete Evidence Locker.
    """
    from app.db import repository

    report = EmbeddingRunReport(attempted=len(evidence_rows))
    if provider is None:
        report.skipped = True
        report.persisted_rows = repository.embedding_row_count(conn)
        return report

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative")
    if initial_retry_delay_seconds < 0:
        raise ValueError("initial_retry_delay_seconds cannot be negative")

    expected_dimensions: int | None = None

    for start in range(0, len(evidence_rows), batch_size):
        batch = evidence_rows[start : start + batch_size]
        ids = [row[0] for row in batch]
        texts = [row[1] for row in batch]
        vectors: list[list[float]] | None = None
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                candidate_vectors = provider.embed_batch(texts)
                vectors, expected_dimensions = _validate_batch(
                    candidate_vectors, len(ids), expected_dimensions
                )
                break
            except ValueError as exc:
                # A malformed response is not transient. Retrying it would only
                # hide a provider-contract mismatch and waste the rate-limit budget.
                last_error = exc
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(initial_retry_delay_seconds * (2**attempt))

        if vectors is None:
            report.error = (
                f"embedding batch {start // batch_size + 1} failed after "
                f"{max_retries + 1} attempt(s): {last_error}"
            )
            break

        for evidence_id, vector in zip(ids, vectors, strict=True):
            repository.insert_embedding(conn, evidence_id, provider.model_name, json.dumps(vector))
            report.succeeded += 1

    report.persisted_rows = repository.embedding_row_count(conn)
    return report


def _validate_batch(
    candidate_vectors: list[list[float]], expected_count: int, expected_dimensions: int | None
) -> tuple[list[list[float]], int]:
    if len(candidate_vectors) != expected_count:
        raise ValueError(
            "embedding provider returned "
            f"{len(candidate_vectors)} vectors for {expected_count} evidence units"
        )

    validated: list[list[float]] = []
    dimensions = expected_dimensions
    for index, vector in enumerate(candidate_vectors):
        try:
            numeric = np.asarray(vector, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"embedding vector {index} is not numeric") from exc

        if numeric.ndim != 1 or numeric.size == 0:
            raise ValueError(f"embedding vector {index} must be a non-empty one-dimensional vector")
        if not np.isfinite(numeric).all():
            raise ValueError(f"embedding vector {index} contains a non-finite value")
        if dimensions is None:
            dimensions = int(numeric.size)
        elif numeric.size != dimensions:
            raise ValueError(
                f"embedding vector {index} has dimension {numeric.size}; expected {dimensions}"
            )
        validated.append(numeric.tolist())

    # expected_count can only be zero when this helper is called directly in a
    # future adapter test. Ingestion never emits an empty batch.
    if dimensions is None:
        raise ValueError("embedding batch contains no vectors")
    return validated, dimensions
