"""Embedding generation.

Must never make the rest of ingestion depend on network access:
--skip-embeddings and a deterministic mock provider let schema, parsing,
FTS, and people/alias work fully offline (CLAUDE.md 8.1). A provider
failure is reported, not raised, so deterministic ingestion output still
succeeds when embeddings do not.

The organizer contract has been verified as OpenAI-compatible: HTTPS
``/v1/embeddings``, bearer authentication, ``{model, input}`` requests, and
``data`` responses containing numeric embedding vectors. The provider below
keeps that transport at the same narrow boundary as the offline mock.
"""

import hashlib
import json
import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx
import numpy as np

_LOGGER = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    model_name: str

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingTransientError(RuntimeError):
    """A provider response that can be retried by ``generate_embeddings``."""


class EmbeddingPermanentError(ValueError):
    """A safe, non-retryable provider failure category."""


class OpenAICompatibleEmbeddingProvider:
    """Minimal adapter for the verified organizer embedding contract.

    It logs only status, request ID, and batch size. Request text, API keys,
    response bodies, and vectors are intentionally never written to logs.
    """

    _TRANSIENT_STATUS_CODES = frozenset({408, 425, 429})

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 30.0,
        request: Callable[..., httpx.Response] = httpx.post,
    ) -> None:
        if not api_key or not base_url or not model_name:
            raise ValueError("complete API key, base URL, and embedding model are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.model_name = model_name
        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/embeddings"
        self._timeout_seconds = timeout_seconds
        self._request = request

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            response = self._request(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model_name, "input": texts},
                timeout=self._timeout_seconds,
            )
        except httpx.RequestError as exc:
            _LOGGER.warning(
                "embedding transport failure error_type=%s batch_size=%s",
                type(exc).__name__,
                len(texts),
            )
            raise EmbeddingTransientError("embedding transport failure") from exc

        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        _LOGGER.info(
            "embedding response status=%s request_id=%s batch_size=%s",
            response.status_code,
            request_id or "missing",
            len(texts),
        )
        if not response.is_success:
            message = f"embedding API returned HTTP {response.status_code}"
            if response.status_code in self._TRANSIENT_STATUS_CODES or response.status_code >= 500:
                raise EmbeddingTransientError(message)
            raise EmbeddingPermanentError(message)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("embedding API returned a non-JSON response") from exc

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise ValueError("embedding API returned an invalid data array")
        if not all(isinstance(item, dict) and "embedding" in item for item in data):
            raise ValueError("embedding API response is missing embedding vectors")

        indexed = ["index" in item for item in data]
        if any(indexed) and not all(indexed):
            raise ValueError("embedding API response mixes indexed and unindexed vectors")
        if not any(indexed):
            return [item["embedding"] for item in data]

        try:
            ordered = sorted((int(item["index"]), item["embedding"]) for item in data)
        except (TypeError, ValueError) as exc:
            raise ValueError("embedding API returned an invalid vector index") from exc
        if [index for index, _ in ordered] != list(range(len(texts))):
            raise ValueError("embedding API returned incomplete or duplicate vector indexes")
        return [vector for _, vector in ordered]


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
            if isinstance(last_error, EmbeddingPermanentError):
                category = "permanent provider failure"
            elif isinstance(last_error, ValueError):
                category = "response validation failed"
            else:
                category = "provider failure"
            report.error = f"embedding batch {start // batch_size + 1} {category}"
            break

        try:
            _persist_embedding_batch(conn, ids, vectors, provider.model_name)
        except sqlite3.Error:
            # Do not surface raw SQLite error text: drivers may include SQL or
            # values, and this report must never become a personal-data dump.
            report.error = f"embedding batch {start // batch_size + 1} persistence failed"
            break
        report.succeeded += len(ids)

    report.persisted_rows = repository.embedding_row_count(conn)
    return report


def _persist_embedding_batch(
    conn: sqlite3.Connection,
    evidence_ids: list[str],
    vectors: list[list[float]],
    model_name: str,
) -> None:
    """Write one validated provider batch atomically.

    Earlier batches intentionally survive a later provider failure so the
    report can describe incomplete semantic coverage. Within a single batch,
    however, a persistence failure must leave no misleading partial prefix.
    """
    from app.db import repository

    conn.execute("SAVEPOINT embedding_batch")
    try:
        for evidence_id, vector in zip(evidence_ids, vectors, strict=True):
            repository.insert_embedding(conn, evidence_id, model_name, json.dumps(vector))
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT embedding_batch")
        conn.execute("RELEASE SAVEPOINT embedding_batch")
        raise
    else:
        conn.execute("RELEASE SAVEPOINT embedding_batch")


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
