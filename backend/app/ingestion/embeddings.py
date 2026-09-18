"""Embedding generation.

Must never make the rest of ingestion depend on network access:
--skip-embeddings and a deterministic mock provider let schema, parsing,
FTS, and people/alias work fully offline (CLAUDE.md 8.1). A provider
failure is reported, not raised, so deterministic ingestion output still
succeeds when embeddings do not.
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


class GeminiEmbeddingProvider:
    """Batched, retried calls to the Google GenAI embedding endpoint.
    Unverified against a live key as of Phase 1 -- no GOOGLE_API_KEY was
    available in this environment, so only the mock-provider path has
    actually been exercised. See the integration smoke test, which skips
    itself when no key is configured."""

    def __init__(
        self, api_key: str, model_name: str, batch_size: int = 32, max_retries: int = 3
    ) -> None:
        from google import genai  # lazy import: mock/offline paths never need this installed

        self._client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_retries = max_retries

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_chunk_with_retry(texts[start : start + self.batch_size]))
        return vectors

    def _embed_chunk_with_retry(self, chunk: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.models.embed_content(model=self.model_name, contents=chunk)
                return [item.values for item in response.embeddings]
            except Exception as exc:  # transient network/rate-limit failures
                last_error = exc
                time.sleep(2**attempt)
        raise RuntimeError(
            f"embedding request failed after {self.max_retries} attempts"
        ) from last_error


@dataclass
class EmbeddingRunReport:
    attempted: int = 0
    succeeded: int = 0
    skipped: bool = False
    error: str | None = None


def generate_embeddings(
    conn, evidence_rows: list[tuple[str, str]], provider: EmbeddingProvider | None
) -> EmbeddingRunReport:
    """evidence_rows: (evidence_id, raw_text) pairs. provider=None means
    --skip-embeddings; a provider that raises is caught and reported
    rather than allowed to fail the whole ingestion run."""
    from app.db import repository

    report = EmbeddingRunReport(attempted=len(evidence_rows))
    if provider is None:
        report.skipped = True
        return report

    try:
        ids = [row[0] for row in evidence_rows]
        texts = [row[1] for row in evidence_rows]
        vectors = provider.embed_batch(texts)
        for evidence_id, vector in zip(ids, vectors, strict=True):
            repository.insert_embedding(conn, evidence_id, provider.model_name, json.dumps(vector))
            report.succeeded += 1
    except Exception as exc:
        report.error = str(exc)
    return report
